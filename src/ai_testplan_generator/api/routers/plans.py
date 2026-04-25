"""Test plan generation endpoints (M07).

POST   /projects/{project_id}/plans              start autonomous run → 202
GET    /projects/{project_id}/plans              list plans
GET    /projects/{project_id}/plans/{plan_id}    full plan or summary
GET    /projects/{project_id}/plans/{plan_id}/export.json  download
GET    /projects/{project_id}/plans/{plan_id}/coverage     coverage matrix
DELETE /projects/{project_id}/plans/{plan_id}   remove plan
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_event_broker,
    get_jobs,
    get_plans,
    get_project_plans,
    get_settings,
)
from ai_testplan_generator.api.errors import NotFoundError
from ai_testplan_generator.api.jobs import Job, JobStatus
from ai_testplan_generator.api.schemas.plans import (
    CoverageMatrixResponse,
    CreatePlanAccepted,
    CreatePlanRequest,
    PlanListItem,
    PlanListResponse,
    TestPlanSummary,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.models import DetailLevel, TestPlan
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["plans"])


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

async def _run_autonomous(
    job: Job,
    brain: Brain,
    broker: InMemoryEventBroker,
    blob_store: BlobStore,
    plans: dict[str, TestPlan],
    project_plans: dict[str, list[str]],
    *,
    project_id: str,
    goal: str,
    detail_level: DetailLevel,
    max_revision_rounds: int,
    session_id: str,
) -> None:
    job.start()
    topic_job = f"job:{job.id}"
    topic_sess = f"session:{session_id}"

    try:
        await broker.publish(topic_sess, {"kind": "agent_start", "actor": "orchestrator",
                                          "content": "Starting autonomous plan generation."})
        from ai_testplan_generator.pipelines.autonomous import AutonomousPipeline

        pipeline = AutonomousPipeline(brain)
        result = await pipeline.run(
            project_id=project_id,
            goal=goal,
            detail_level=detail_level,
            max_revision_rounds=max_revision_rounds,
            session_id=session_id,
        )
        plan = result.plan
        if plan is None:
            raise RuntimeError("Pipeline completed without producing a plan.")

        # Persist to blob store.
        plan_key = f"projects/{project_id}/plans/{plan.id}.json"
        await blob_store.put(plan_key, plan.model_dump_json().encode(), "application/json")

        # Register in in-process index.
        plans[plan.id] = plan
        project_plans.setdefault(project_id, []).append(plan.id)

        res: dict[str, Any] = {"plan_id": plan.id, "n_test_cases": len(plan.test_cases)}
        job.succeed(res)
        await broker.publish(topic_sess, {"kind": "agent_done", "actor": "orchestrator",
                                          "content": "Plan generation complete.",
                                          "metadata": res})
        await broker.publish(topic_job, {"kind": "job_succeeded", **res})
        _log.info("plan_done", session_id=session_id, plan_id=plan.id)
    except Exception as exc:
        job.fail(str(exc))
        await broker.publish(topic_sess, {"kind": "agent_error", "actor": "orchestrator",
                                          "content": str(exc)})
        await broker.publish(topic_job, {"kind": "job_failed", "error": str(exc)})
        _log.error("plan_error", session_id=session_id, error=str(exc))
    finally:
        await broker.close_topic(topic_job)
        await broker.close_topic(topic_sess)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/plans",
    status_code=202,
    response_model=CreatePlanAccepted,
    summary="Start autonomous test plan generation",
)
async def create_plan(
    project_id: str,
    body: CreatePlanRequest,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    jobs: Annotated[dict[str, Job], Depends(get_jobs)],
    broker: Annotated[InMemoryEventBroker, Depends(get_event_broker)],
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    project_plans: Annotated[dict[str, list[str]], Depends(get_project_plans)],
) -> CreatePlanAccepted:
    from uuid import uuid4

    session_id = f"sess_{uuid4().hex[:10]}"
    job = Job(kind="run_autonomous", session_id=session_id)
    jobs[job.id] = job

    asyncio.create_task(
        _run_autonomous(
            job, brain, broker, blob_store, plans, project_plans,
            project_id=project_id,
            goal=body.goal,
            detail_level=body.detail_level,
            max_revision_rounds=body.max_revision_rounds,
            session_id=session_id,
        )
    )
    return CreatePlanAccepted(job_id=job.id, session_id=session_id)


@router.get(
    "/projects/{project_id}/plans",
    response_model=PlanListResponse,
    summary="List plans for a project",
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
)
async def export_plan_json(
    project_id: str,
    plan_id: str,
    plans: Annotated[dict[str, TestPlan], Depends(get_plans)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> Response:
    plan = plans.get(plan_id)
    if plan is None:
        # Try loading from blob store.
        key = f"projects/{project_id}/plans/{plan_id}.json"
        try:
            raw = await blob_store.get(key)
            return Response(content=raw, media_type="application/json",
                            headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'})
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
)
async def get_plan(
    project_id: str,
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
