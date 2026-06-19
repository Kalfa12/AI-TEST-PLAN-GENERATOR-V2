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
    get_job_queue,
    get_plans,
)
from ai_testplan_generator.api.errors import NotFoundError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.api.schemas.plans import (
    CheckpointResponse,
    CoverageMatrixResponse,
    CreatePlanAccepted,
    CreatePlanRequest,
    PlanListItem,
    PlanListResponse,
    ResumeRequest,
    TestPlanSummary,
)
from ai_testplan_generator.jobs.queue import JobQueueProtocol
from ai_testplan_generator.models import TestPlan
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["plans"])


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
    plan = plans.get(plan_id) or await brain.memory.get_test_plan(plan_id)
    if plan is None:
        key = f"projects/{project_id}/plans/{plan_id}.json"
        try:
            raw = await blob_store.get(key)
            return Response(
                content=raw,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'},
            )
        except Exception:
            raise NotFoundError(f"Plan '{plan_id}' not found.")
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
    plan = plans.get(plan_id) or await brain.memory.get_test_plan(plan_id)
    if plan is None:
        raise NotFoundError(f"Plan '{plan_id}' not found.")
    req_ids = list(plan.coverage_matrix.keys())
    if not req_ids:
        req_ids = list({rid for tc in plan.test_cases for rid in tc.requirement_ids})
    matrix = brain.memory.graph.coverage_matrix(req_ids)
    if not any(matrix.values()) and plan.coverage_matrix:
        matrix = plan.coverage_matrix
    return CoverageMatrixResponse(plan_id=plan_id, matrix=matrix)


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
    plan = plans.get(plan_id) or await brain.memory.get_test_plan(plan_id)
    if plan is None:
        raise NotFoundError(f"Plan '{plan_id}' not found.")
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
    dependencies=[Depends(get_current_user)],
)
async def get_job_checkpoint(
    job_id: str,
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> CheckpointResponse:
    from ai_testplan_generator.api.errors import NotFoundError, ValidationError

    job = await job_queue.get_status(job_id)
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
    dependencies=[Depends(get_current_user)],
)
async def resume_job(
    job_id: str,
    body: ResumeRequest,
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
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

    job = await job_queue.get_status(job_id)
    ok = submit_directive(
        job,
        ResumeDirective(action=body.action, feedback=body.feedback),
    )
    if not ok:
        raise ValidationError(
            f"Job '{job_id}' is not currently paused at a checkpoint."
        )

    return JobStatusResponse.from_job(job)
