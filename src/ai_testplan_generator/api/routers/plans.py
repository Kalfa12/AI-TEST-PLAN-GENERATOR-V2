"""Test plan generation endpoints (M07).

POST   /projects/{project_id}/plans              start autonomous run → 202
GET    /projects/{project_id}/plans              list plans
GET    /projects/{project_id}/plans/{plan_id}    full plan or summary
GET    /projects/{project_id}/plans/{plan_id}/export.json  download
GET    /projects/{project_id}/plans/{plan_id}/coverage     coverage matrix
DELETE /projects/{project_id}/plans/{plan_id}   remove plan
"""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_job_queue,
    get_plans,
    get_project_plans,
)
from ai_testplan_generator.api.errors import NotFoundError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.api.schemas.plans import (
    CoverageMatrixResponse,
    CreatePlanAccepted,
    CreatePlanRequest,
    JobStatusResponse,
    PlanListItem,
    PlanListResponse,
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
    job_id = await job_queue.enqueue(
        "run_autonomous",
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
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    project_plans: Annotated[dict[str, list[str]], Depends(get_project_plans)],
) -> PlanListResponse:
    ids = project_plans.get(project_id, [])
    items = [
        PlanListItem(
            id=p.id,
            title=p.title,
            detail_level=p.detail_level.value,
            n_test_cases=len(p.test_cases),
        )
        for pid in ids
        if (p := plans.get(pid)) is not None
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
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> Response:
    plan = plans.get(plan_id)
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
    plan = plans.get(plan_id)
    if plan is None:
        raise NotFoundError(f"Plan '{plan_id}' not found.")
    req_ids = list(plan.coverage_matrix.keys())
    if not req_ids:
        req_ids = list({rid for tc in plan.test_cases for rid in tc.requirement_ids})
    matrix = brain.memory.graph.coverage_matrix(req_ids)
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
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    detail: Annotated[str | None, Query()] = None,
) -> TestPlan | TestPlanSummary:
    plan = plans.get(plan_id)
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
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    project_plans: Annotated[dict[str, list[str]], Depends(get_project_plans)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> None:
    if plan_id not in plans:
        raise NotFoundError(f"Plan '{plan_id}' not found.")
    plans.pop(plan_id, None)
    ids = project_plans.get(project_id, [])
    if plan_id in ids:
        ids.remove(plan_id)
    try:
        key = f"projects/{project_id}/plans/{plan_id}.json"
        await blob_store.delete(key)
    except Exception:
        pass


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll background job status (plan generation, ingest)",
)
async def get_job_status(
    job_id: str,
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> JobStatusResponse:
    job = await job_queue.get_status(job_id)
    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        result=job.result,
        error=job.error,
    )
