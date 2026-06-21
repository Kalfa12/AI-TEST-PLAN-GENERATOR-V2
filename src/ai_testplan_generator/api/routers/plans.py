"""Test plan generation endpoints (M07).

POST   /projects/{project_id}/plans              start autonomous run → 202
GET    /projects/{project_id}/plans              list plans
GET    /projects/{project_id}/plans/{plan_id}    full plan or summary
GET    /projects/{project_id}/plans/{plan_id}/export.json  download
GET    /projects/{project_id}/plans/{plan_id}/coverage     coverage matrix
DELETE /projects/{project_id}/plans/{plan_id}   remove plan
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_current_user,
    get_defects,
    get_job_repo,
    get_job_queue,
    get_plans,
    get_project_repo,
)
from ai_testplan_generator.api.errors import NotFoundError, ValidationError
from ai_testplan_generator.api.security.projects import ensure_project_access
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.api.schemas.plans import (
    CheckpointResponse,
    CoverageMatrixResponse,
    CreatePlanAccepted,
    CreatePlanRequest,
    GenerateRequirementTestCaseRequest,
    GenerateRequirementTestCaseResponse,
    PlanListItem,
    PlanListResponse,
    ResumeRequest,
    TestCaseSummary,
    TestPlanSummary,
)
from ai_testplan_generator.agents.test_generator import TestGeneratorAgent
from ai_testplan_generator.agents.traceability import TraceabilityAgent
from ai_testplan_generator.jobs.queue import JobQueueProtocol
from ai_testplan_generator.domain.jobs import JobRepository
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.models import TestPlan
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["plans"])


async def _get_project_plan(
    *,
    project_id: str,
    plan_id: str,
    brain: Brain,
    plans: dict[str, TestPlan],
) -> TestPlan:
    plan = plans.get(plan_id) or await brain.memory.get_test_plan(plan_id)
    if plan is None or plan.project_id != project_id:
        raise NotFoundError(f"Plan '{plan_id}' not found in project '{project_id}'.")
    return plan


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/plans",
    status_code=202,
    response_model=CreatePlanAccepted,
    summary="Start autonomous test plan generation",
    dependencies=[Depends(require("plan.generate"))],
)
async def create_plan(
    project_id: str,
    body: CreatePlanRequest,
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> CreatePlanAccepted:
    session_id = f"sess_{uuid4().hex[:10]}"
    task_name = "run_autonomous_interactive" if body.interactive else "run_autonomous"
    job_id = await job_queue.enqueue(
        task_name,
        project_id=project_id,
        goal=body.goal,
        detail_level=body.detail_level.value,
        max_revision_rounds=body.max_revision_rounds,
        session_id=session_id,
    )
    return CreatePlanAccepted(job_id=job_id, session_id=session_id)


@router.get(
    "/projects/{project_id}/plans",
    response_model=PlanListResponse,
    summary="List plans for a project",
    dependencies=[Depends(require("plan.read"))],
)
async def list_plans(
    project_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> PlanListResponse:
    project_plans = await brain.memory.get_test_plans_for_project(project_id)
    items = [
        PlanListItem(
            id=p.id,
            title=p.title,
            detail_level=p.detail_level.value,
            n_test_cases=len(p.test_cases),
        )
        for p in project_plans
    ]
    return PlanListResponse(items=items, total=len(items))


@router.get(
    "/projects/{project_id}/plans/{plan_id}/export.json",
    summary="Download plan as JSON",
    dependencies=[Depends(require("plan.read"))],
)
async def export_plan_json(
    project_id: str,  # noqa: ARG001
    plan_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> Response:
    try:
        plan = await _get_project_plan(
            project_id=project_id, plan_id=plan_id, brain=brain, plans=plans
        )
    except NotFoundError:
        key = f"projects/{project_id}/plans/{plan_id}.json"
        try:
            raw = await blob_store.get(key)
            return Response(
                content=raw,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'},
            )
        except Exception:
            raise
    return Response(
        content=plan.model_dump_json().encode(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'},
    )


@router.get(
    "/projects/{project_id}/plans/{plan_id}/coverage",
    response_model=CoverageMatrixResponse,
    summary="Coverage matrix for a plan",
    dependencies=[Depends(require("plan.read"))],
)
async def plan_coverage(
    project_id: str,
    plan_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
) -> CoverageMatrixResponse:
    plan = await _get_project_plan(
        project_id=project_id, plan_id=plan_id, brain=brain, plans=plans
    )
    req_ids = list(plan.coverage_matrix.keys())
    if not req_ids:
        req_ids = list({rid for tc in plan.test_cases for rid in tc.requirement_ids})
    matrix = brain.memory.graph.coverage_matrix(req_ids)
    if not any(matrix.values()) and plan.coverage_matrix:
        matrix = plan.coverage_matrix
    return CoverageMatrixResponse(plan_id=plan_id, matrix=matrix)


@router.post(
    "/projects/{project_id}/plans/{plan_id}/requirements/{requirement_id}/test-case",
    response_model=GenerateRequirementTestCaseResponse,
    summary="Generate one test case to repair requirement coverage",
    dependencies=[Depends(require("plan.generate"))],
)
async def generate_requirement_test_case(
    project_id: str,
    plan_id: str,
    requirement_id: str,
    body: GenerateRequirementTestCaseRequest,
    brain: Annotated[Brain, Depends(get_brain)],
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    defects: Annotated[dict[str, Any], Depends(get_defects)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> GenerateRequirementTestCaseResponse:
    plan = await _get_project_plan(
        project_id=project_id, plan_id=plan_id, brain=brain, plans=plans
    )
    if plan.project_id != project_id:
        raise NotFoundError(f"Plan '{plan_id}' not found in project '{project_id}'.")

    requirements = await brain.memory.get_requirements_for_project(project_id)
    requirement = next((req for req in requirements if req.id == requirement_id), None)
    if requirement is None:
        raise NotFoundError(
            f"Requirement '{requirement_id}' not found in project '{project_id}'."
        )

    ctx = brain.context(
        session_id=f"repair_{uuid4().hex[:10]}",
        project_id=project_id,
    )
    generator = TestGeneratorAgent(ctx)
    feedback = [body.feedback] if body.feedback else []
    generated = await generator.invoke(
        TestGeneratorAgent.Input(
            requirements=[requirement],
            detail_level=plan.detail_level,
            concurrency=1,
            user_feedback=feedback,
        )
    )
    if not generated.test_cases:
        raise ValidationError(
            f"Could not generate a test case for requirement '{requirement_id}'."
        )

    test_case = generated.test_cases[0]
    plan.test_cases.append(test_case)

    trace = await TraceabilityAgent(ctx).invoke(
        TraceabilityAgent.Input(plan=plan, requirements=requirements)
    )
    plan.coverage_matrix = trace.coverage_matrix
    await brain.memory.register_test_plan(plan)
    plans[plan.id] = plan

    defects.pop(plan.id, None)
    try:
        await blob_store.delete(f"projects/{project_id}/plans/{plan.id}.defects.json")
    except Exception:
        pass

    return GenerateRequirementTestCaseResponse(
        plan_id=plan.id,
        requirement_id=requirement.id,
        test_case=TestCaseSummary(
            id=test_case.id,
            title=test_case.title,
            objective=test_case.objective,
            requirement_ids=test_case.requirement_ids,
            risk_level=test_case.risk_level,
            risk_description=test_case.risk_description,
            estimated_duration_minutes=test_case.estimated_duration_minutes,
            assignee=test_case.assignee,
            status=test_case.status,
            status_note=test_case.status_note,
            tags=test_case.tags,
            source_evidence=[
                ev.model_dump(mode="json") for ev in test_case.source_evidence
            ],
        ),
        coverage_matrix=plan.coverage_matrix,
    )


@router.get(
    "/projects/{project_id}/plans/{plan_id}",
    response_model=None,
    summary="Get plan (full or summary)",
    dependencies=[Depends(require("plan.read"))],
)
async def get_plan(
    project_id: str,  # noqa: ARG001
    plan_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    detail: Annotated[str | None, Query()] = None,
) -> TestPlan | TestPlanSummary:
    plan = await _get_project_plan(
        project_id=project_id, plan_id=plan_id, brain=brain, plans=plans
    )
    if detail == "summary":
        return TestPlanSummary.from_plan(plan)
    return plan


@router.delete(
    "/projects/{project_id}/plans/{plan_id}",
    status_code=204,
    summary="Delete a plan",
    dependencies=[Depends(require("plan.generate"))],
)
async def delete_plan(
    project_id: str,
    plan_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> None:
    plan = plans.get(plan_id) or await brain.memory.get_test_plan(plan_id)
    if plan is None:
        raise NotFoundError(f"Plan '{plan_id}' not found.")
    plans.pop(plan_id, None)
    await brain.memory.delete_test_plan(plan_id)
    try:
        key = f"projects/{project_id}/plans/{plan_id}.json"
        await blob_store.delete(key)
    except Exception:
        pass


# Note: GET /jobs/{job_id} lives in routers/events.py (single canonical
# implementation). Adding a duplicate here previously caused the test suite
# and the frontend to disagree on field names (`id` vs `job_id`).


@router.get(
    "/jobs/{job_id}/checkpoint",
    response_model=CheckpointResponse,
    summary="Fetch the paused state of an interactive run",
)
async def get_job_checkpoint(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
    job_repo: Annotated[JobRepository, Depends(get_job_repo)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> CheckpointResponse:
    from ai_testplan_generator.api.errors import NotFoundError, ValidationError

    stored = await job_repo.get_checkpoint(job_id)
    if stored is not None:
        stored_job = await job_repo.get_job(job_id)
        await ensure_project_access(
            project_id=stored_job.project_id if stored_job else None,
            current_user=current_user,
            project_repo=project_repo,
        )
        return CheckpointResponse(
            job_id=stored.job_id,
            paused_at=stored.paused_at,
            state=stored.state,
        )

    job = await job_queue.get_status(job_id)
    await ensure_project_access(
        project_id=job.project_id,
        current_user=current_user,
        project_repo=project_repo,
    )
    paused_at = getattr(job, "paused_at", None)
    paused_state = getattr(job, "paused_state", None)

    if paused_at is None or paused_state is None:
        raise ValidationError(f"Job '{job_id}' is not paused at a checkpoint.")

    # AutonomousState is a Pydantic model — model_dump() gives a JSON-safe dict.
    try:
        state_dump = paused_state.model_dump(mode="json")
    except AttributeError as exc:
        raise NotFoundError(f"Job '{job_id}' has no checkpoint state.") from exc

    return CheckpointResponse(
        job_id=job.id, paused_at=paused_at, state=state_dump
    )


@router.post(
    "/jobs/{job_id}/resume",
    summary="Resume a paused interactive run with accept / reprompt / abort",
)
async def resume_job(
    job_id: str,
    body: ResumeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
    job_repo: Annotated[JobRepository, Depends(get_job_repo)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> Any:
    from ai_testplan_generator.api.errors import ValidationError
    from ai_testplan_generator.api.routers.events import JobStatusResponse
    from ai_testplan_generator.pipelines.interactive_run import (
        ResumeDirective,
        submit_directive,
    )

    if body.action not in ("accept", "reprompt", "abort"):
        raise ValidationError(
            f"Invalid action '{body.action}'. Use accept | reprompt | abort."
        )
    if body.action == "reprompt" and not (body.feedback and body.feedback.strip()):
        raise ValidationError("Reprompt requires non-empty feedback text.")

    checkpoint = await job_repo.get_checkpoint(job_id)
    job = await job_queue.get_status(job_id)
    project_id = job.project_id
    if project_id is None and checkpoint is not None:
        stored_job = await job_repo.get_job(job_id)
        project_id = stored_job.project_id if stored_job else None
    await ensure_project_access(
        project_id=project_id,
        current_user=current_user,
        project_repo=project_repo,
    )
    if checkpoint is None and getattr(job, "paused_at", None) is None:
        raise ValidationError(
            f"Job '{job_id}' is not currently paused at a checkpoint."
        )

    directive = {"action": body.action, "feedback": body.feedback}
    ok = submit_directive(
        job,
        ResumeDirective(action=body.action, feedback=body.feedback),
    )
    if ok:
        try:
            await job_repo.save_resume_directive(job_id, directive)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "resume_directive_persist_failed",
                job_id=job_id,
                error=str(exc),
            )
    else:
        if checkpoint is None:
            raise ValidationError(
                f"Job '{job_id}' is not currently paused at a checkpoint."
            )
        await job_repo.save_resume_directive(job_id, directive)

    return JobStatusResponse.from_job(job)
