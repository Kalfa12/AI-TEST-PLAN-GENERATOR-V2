"""Defect / quality endpoints.

GET  /jobs/{job_id}/defects                                 → DefectReport for a running/completed job
GET  /projects/{project_id}/plans/{plan_id}/defects         → DefectReport for a persisted plan
GET  /quality/catalog                                       → DefectCatalog metadata (static)
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends

from ai_testplan_generator.api.deps import get_blob_store, get_defects, get_job_queue
from ai_testplan_generator.api.errors import NotFoundError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.jobs.queue import JobQueueProtocol
from ai_testplan_generator.models import CATALOG, DefectReport
from ai_testplan_generator.storage.base import BlobStore

router = APIRouter(tags=["quality"])


@router.get(
    "/quality/catalog",
    summary="Static defect taxonomy catalog (ISO 29148 / 29119 / INCOSE).",
)
async def get_catalog() -> dict[str, list[dict]]:
    return {
        "entries": [
            entry.model_dump(mode="json") for entry in CATALOG.values()
        ]
    }


@router.get(
    "/projects/{project_id}/plans/{plan_id}/defects",
    response_model=DefectReport,
    summary="Defect report for a completed plan",
    dependencies=[Depends(require("plan.read"))],
)
async def get_plan_defects(
    project_id: str,
    plan_id: str,
    defects: Annotated[dict[str, DefectReport], Depends(get_defects)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> DefectReport:
    cached = defects.get(plan_id)
    if cached is not None:
        return cached
    key = f"projects/{project_id}/plans/{plan_id}.defects.json"
    try:
        raw = await blob_store.get(key)
    except Exception as exc:
        raise NotFoundError(
            f"No defect report for plan '{plan_id}'."
        ) from exc
    report = DefectReport.model_validate(json.loads(raw))
    defects[plan_id] = report
    return report


@router.get(
    "/jobs/{job_id}/defects",
    response_model=DefectReport,
    summary="Defect report for an in-flight or paused job",
)
async def get_job_defects(
    job_id: str,
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> DefectReport:
    job = await job_queue.get_status(job_id)
    paused_state = getattr(job, "paused_state", None)
    if paused_state is not None and getattr(paused_state, "defect_report", None) is not None:
        return paused_state.defect_report  # type: ignore[no-any-return]
    if job.result and isinstance(job.result, dict):
        plan_id = job.result.get("plan_id")
        if plan_id:
            raise NotFoundError(
                f"Job '{job_id}' has finished — fetch the defect report via "
                f"/projects/{{project_id}}/plans/{plan_id}/defects."
            )
    raise NotFoundError(f"No defect report available for job '{job_id}'.")
