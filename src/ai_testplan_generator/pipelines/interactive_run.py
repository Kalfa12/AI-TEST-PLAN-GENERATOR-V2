"""Interactive autonomous run.

Mirrors `AutonomousPipeline` but runs the agents sequentially in-process,
pausing for user feedback at three checkpoints: extractor, architect,
generator. The `Job` object owns the pause/resume signalling; the
HTTP layer (`/jobs/{id}/checkpoint`, `/jobs/{id}/resume`) drives it.

This pipeline still needs a live in-process task to continue immediately,
but every checkpoint is also written to the durable job repository so the
API can inspect paused state after an application restart.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import structlog

from ai_testplan_generator.agents import AutonomousState, build_defect_report
from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.document_analyst import DocumentAnalystAgent
from ai_testplan_generator.agents.planner import PlannerAgent
from ai_testplan_generator.agents.requirement_extractor import RequirementExtractorAgent
from ai_testplan_generator.agents.requirement_reviewer import RequirementReviewerAgent
from ai_testplan_generator.agents.reviewer import ReviewerAgent
from ai_testplan_generator.agents.test_architect import TestArchitectAgent
from ai_testplan_generator.agents.test_generator import TestGeneratorAgent
from ai_testplan_generator.agents.traceability import TraceabilityAgent
from ai_testplan_generator.api.jobs import Job, JobStatus
from ai_testplan_generator.domain.jobs import JobRepository
from ai_testplan_generator.models import Chunk, DefectReport, DetailLevel, TestPlan
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.quality import check_requirements, check_test_plan

_log = structlog.get_logger(__name__)


# The three agents that gate user review. Ordered as they execute.
CHECKPOINT_AGENTS = ("extractor", "architect", "generator")


class ResumeAborted(Exception):
    """Raised when a paused job is cancelled (user closed the tab without
    accepting). The run task exits cleanly."""


@dataclass
class ResumeDirective:
    """Captured by the resume endpoint, consumed by the run task."""
    action: str  # "accept" | "reprompt" | "abort"
    feedback: str | None = None


async def run_interactive(
    *,
    brain: Brain,
    job: Job,
    project_id: str,
    goal: str,
    detail_level: DetailLevel,
    max_revision_rounds: int,
    session_id: str,
    job_repo: JobRepository | None = None,
) -> dict[str, Any]:
    """Execute the autonomous pipeline with user-gated checkpoints.

    The run is driven from this single coroutine. After each gated
    agent it stores AutonomousState on the Job and awaits a resume
    signal. The resume endpoint sets `job.paused_state.interactive_directive`
    on the state, then sets the asyncio.Event the run task is waiting on.
    """
    ctx: AgentContext = brain.context(session_id=session_id, project_id=project_id)
    docs = await brain.memory.get_documents_for_project(project_id)
    reqs_existing = await brain.memory.get_requirements_for_project(project_id)

    state = AutonomousState(
        session_id=session_id,
        project_id=project_id,
        goal=goal,
        detail_level=detail_level,
        documents=docs,
        requirements=reqs_existing,
        max_revision_rounds=max_revision_rounds,
        interactive=True,
    )

    # Eagerly gather chunks once — used by analyst + extractor.
    project_chunks: list[Chunk] = []
    for d in docs:
        project_chunks.extend(await brain.memory.get_chunks_for_document(d.id))
    if not project_chunks:
        raise RuntimeError("no chunks available for requirement extraction")

    # ---- step: analyst (no checkpoint, low value to gate)
    analyst = DocumentAnalystAgent(ctx)
    await analyst.invoke(DocumentAnalystAgent.Input(documents=state.documents))

    # ---- step: extractor (CHECKPOINT)
    while True:
        feedback = state.user_feedback.get("extractor", [])
        extractor = RequirementExtractorAgent(ctx)
        out_e = await extractor.invoke(
            RequirementExtractorAgent.Input(
                chunks=project_chunks, user_feedback=feedback
            )
        )
        state.requirements = out_e.requirements
        if not state.requirements:
            raise RuntimeError(
                "requirement extraction produced no requirements; "
                "cannot generate a grounded test plan"
            )
        _update_partial_defects(state)
        directive = await _await_user(job, agent="extractor", state=state, job_repo=job_repo)
        if directive.action == "accept":
            break
        if directive.action == "abort":
            raise ResumeAborted()
        if directive.action == "reprompt" and directive.feedback:
            state.user_feedback.setdefault("extractor", []).append(directive.feedback)

    # ---- step: architect (CHECKPOINT)
    plan: TestPlan | None = None
    while True:
        feedback = state.user_feedback.get("architect", [])
        architect = TestArchitectAgent(ctx)
        plan = await architect.invoke(
            TestArchitectAgent.Input(
                goal=state.goal,
                detail_level=state.detail_level,
                requirements=state.requirements,
                user_feedback=feedback,
            )
        )
        state.plan = plan
        directive = await _await_user(job, agent="architect", state=state, job_repo=job_repo)
        if directive.action == "accept":
            break
        if directive.action == "abort":
            raise ResumeAborted()
        if directive.action == "reprompt" and directive.feedback:
            state.user_feedback.setdefault("architect", []).append(directive.feedback)

    assert plan is not None  # for type-checker; loop only exits with plan set

    # ---- step: generator (CHECKPOINT)
    while True:
        feedback = state.user_feedback.get("generator", [])
        generator = TestGeneratorAgent(ctx)
        out_g = await generator.invoke(
            TestGeneratorAgent.Input(
                requirements=state.requirements,
                detail_level=state.detail_level,
                user_feedback=feedback,
            )
        )
        plan.test_cases = out_g.test_cases
        state.test_cases = out_g.test_cases
        _update_partial_defects(state)
        directive = await _await_user(job, agent="generator", state=state, job_repo=job_repo)
        if directive.action == "accept":
            break
        if directive.action == "abort":
            raise ResumeAborted()
        if directive.action == "reprompt" and directive.feedback:
            state.user_feedback.setdefault("generator", []).append(directive.feedback)

    # ---- tail: requirement-review + traceability + reviewer + defects + planner
    req_reviewer = RequirementReviewerAgent(ctx)
    req_review_report = await req_reviewer.invoke(
        RequirementReviewerAgent.Input(requirements=state.requirements)
    )
    state.requirement_review_report = req_review_report

    trace = TraceabilityAgent(ctx)
    trace_report = await trace.invoke(
        TraceabilityAgent.Input(plan=plan, requirements=state.requirements)
    )
    state.trace_report = trace_report

    reviewer = ReviewerAgent(ctx)
    review_report = await reviewer.invoke(ReviewerAgent.Input(plan=plan))
    state.review_report = review_report

    state.defect_report = build_defect_report(
        plan=plan,
        requirements=state.requirements,
        review_report=state.review_report,
        requirement_review_report=state.requirement_review_report,
        trace_report=state.trace_report,
    )

    planner = PlannerAgent(ctx)
    schedule = await planner.invoke(PlannerAgent.Input(plan=plan, resources=[]))
    state.schedule = schedule

    return {
        "plan_id": plan.id,
        "n_test_cases": len(plan.test_cases),
        "plan": plan,
        "defect_report": state.defect_report,
    }


async def _await_user(
    job: Job,
    *,
    agent: str,
    state: AutonomousState,
    job_repo: JobRepository | None = None,
) -> ResumeDirective:
    """Pause the run task and wait for the resume endpoint to fire."""
    # Reset the signal each pause so previous resume doesn't leak through.
    signal = asyncio.Event()
    directive_holder: dict[str, ResumeDirective] = {}
    job.resume_signal = signal
    job._resume_directive = directive_holder  # type: ignore[attr-defined]
    job.pause(agent=agent, state=state)
    if job_repo is not None:
        await job_repo.save_checkpoint(
            job=job,
            paused_at=agent,
            state=state.model_dump(mode="json"),
            project_id=state.project_id,
        )
    _log.info("interactive_pause", job_id=job.id, agent=agent)
    await signal.wait()
    job.resume()
    if job_repo is not None:
        await job_repo.delete_checkpoint(job.id)
        await job_repo.save_job(job, project_id=state.project_id)
    return directive_holder.get(
        "directive", ResumeDirective(action="accept")
    )


def submit_directive(job: Job, directive: ResumeDirective) -> bool:
    """Called by the resume HTTP handler. Returns True if signalled."""
    if job.status != JobStatus.PAUSED or job.resume_signal is None:
        return False
    holder = getattr(job, "_resume_directive", None)
    if isinstance(holder, dict):
        holder["directive"] = directive
    job.resume_signal.set()
    return True


# The plan-id helper used by the run task to mint a stable id even if we
# keep the architect's plan; included for future symmetry with the
# autonomous variant.
def make_session_id() -> str:
    return f"sess_{uuid4().hex[:10]}"


def _update_partial_defects(state: AutonomousState) -> None:
    """Refresh the static-checker portion of the defect report on the live state.

    Used at interactive checkpoints so the UI can badge defective rows
    before the full aggregator runs at the tail of the pipeline.
    """
    defects = list(check_requirements(state.requirements))
    if state.plan is not None:
        defects.extend(check_test_plan(state.plan, state.requirements))
    report = DefectReport(
        plan_id=state.plan.id if state.plan else None,
        defects=defects,
    )
    report.compute_summary()
    state.defect_report = report
