"""Interactive autonomous run.

Mirrors `AutonomousPipeline` but runs the agents sequentially in-process,
pausing for user feedback at three checkpoints: extractor, architect,
generator. The `Job` object owns the pause/resume signalling; the
HTTP layer (`/jobs/{id}/checkpoint`, `/jobs/{id}/resume`) drives it.

This pipeline only works with `FakeJobQueue` because the run task
must keep the AutonomousState in process memory between checkpoints.
For ARQ deployment, paused state would have to live in a persistent
checkpointer (Redis/Postgres) — out of scope for v1.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import structlog

from ai_testplan_generator.agents import AutonomousState
from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.document_analyst import DocumentAnalystAgent
from ai_testplan_generator.agents.planner import PlannerAgent
from ai_testplan_generator.agents.requirement_extractor import RequirementExtractorAgent
from ai_testplan_generator.agents.reviewer import ReviewerAgent
from ai_testplan_generator.agents.test_architect import TestArchitectAgent
from ai_testplan_generator.agents.test_generator import TestGeneratorAgent
from ai_testplan_generator.agents.traceability import TraceabilityAgent
from ai_testplan_generator.api.jobs import Job, JobStatus
from ai_testplan_generator.models import Chunk, DetailLevel, TestPlan
from ai_testplan_generator.pipelines.brain import Brain

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
        directive = await _await_user(job, agent="extractor", state=state)
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
        directive = await _await_user(job, agent="architect", state=state)
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
        if not out_g.test_cases:
            raise RuntimeError(
                "generator produced no test cases (all LLM calls failed)"
            )
        plan.test_cases = out_g.test_cases
        state.test_cases = out_g.test_cases
        directive = await _await_user(job, agent="generator", state=state)
        if directive.action == "accept":
            break
        if directive.action == "abort":
            raise ResumeAborted()
        if directive.action == "reprompt" and directive.feedback:
            state.user_feedback.setdefault("generator", []).append(directive.feedback)

    # ---- tail: traceability + reviewer + planner (no checkpoints)
    trace = TraceabilityAgent(ctx)
    trace_report = await trace.invoke(
        TraceabilityAgent.Input(plan=plan, requirements=state.requirements)
    )
    state.trace_report = trace_report

    reviewer = ReviewerAgent(ctx)
    review_report = await reviewer.invoke(ReviewerAgent.Input(plan=plan))
    state.review_report = review_report

    planner = PlannerAgent(ctx)
    schedule = await planner.invoke(PlannerAgent.Input(plan=plan, resources=[]))
    state.schedule = schedule

    return {
        "plan_id": plan.id,
        "n_test_cases": len(plan.test_cases),
        "plan": plan,
    }


async def _await_user(
    job: Job, *, agent: str, state: AutonomousState
) -> ResumeDirective:
    """Pause the run task and wait for the resume endpoint to fire."""
    # Reset the signal each pause so previous resume doesn't leak through.
    signal = asyncio.Event()
    directive_holder: dict[str, ResumeDirective] = {}
    job.resume_signal = signal
    job._resume_directive = directive_holder  # type: ignore[attr-defined]
    job.pause(agent=agent, state=state)
    _log.info("interactive_pause", job_id=job.id, agent=agent)
    await signal.wait()
    job.resume()
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
