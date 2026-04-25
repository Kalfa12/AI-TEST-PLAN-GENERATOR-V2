"""Admin endpoints (M19, M23).

GET  /admin/jobs/deadletter                  list permanently-failed jobs (admin only)
POST /admin/jobs/deadletter/{job_id}/requeue re-enqueue a dead-letter job (admin only)
GET  /admin/costs                            LLM cost summary (admin only)

All routes require the caller to be an admin (``user.is_admin == True``).
Redis-dependent behaviour is gracefully absent when Redis is unavailable.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ai_testplan_generator.api.deps import get_current_user, get_job_queue, get_settings
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.jobs.queue import JobQueueProtocol

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Admin guard
# ---------------------------------------------------------------------------

def _require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DeadLetterEntryResponse(BaseModel):
    job_id: str
    task_name: str
    error: str
    failed_at: str
    job_kwargs: dict[str, Any]


class DeadLetterListResponse(BaseModel):
    items: list[DeadLetterEntryResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/deadletter",
    response_model=DeadLetterListResponse,
    summary="List permanently failed jobs",
)
async def list_dead_letter(
    _admin: Annotated[User, Depends(_require_admin)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> DeadLetterListResponse:
    entries = await job_queue.get_dead_letter_entries()
    items = [
        DeadLetterEntryResponse(
            job_id=e.job_id,
            task_name=e.task_name,
            error=e.error,
            failed_at=e.failed_at,
            job_kwargs=e.kwargs,
        )
        for e in entries
    ]
    return DeadLetterListResponse(items=items, total=len(items))


@router.post(
    "/jobs/deadletter/{job_id}/requeue",
    status_code=202,
    summary="Re-enqueue a permanently failed job",
)
async def requeue_dead_letter(
    job_id: str,
    _admin: Annotated[User, Depends(_require_admin)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> dict[str, str]:
    new_job_id = await job_queue.requeue_dead_letter(job_id)
    _log.info("dead_letter_requeued", old_job_id=job_id, new_job_id=new_job_id)
    return {"job_id": new_job_id}


# ---------------------------------------------------------------------------
# Cost tracking (M23)
# ---------------------------------------------------------------------------


@router.get(
    "/costs",
    summary="LLM cost summary grouped by project, user, or model",
)
async def get_costs(
    _admin: Annotated[User, Depends(_require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    from_ts: str = Query(alias="from", description="ISO-8601 start timestamp (inclusive)"),
    to_ts: str = Query(alias="to", description="ISO-8601 end timestamp (inclusive)"),
    group_by: Literal["project", "user", "model"] = Query(
        default="project",
        description="Dimension to group results by",
    ),
) -> list[dict[str, Any]]:
    from ai_testplan_generator.telemetry.cost import get_cost_summary

    return await get_cost_summary(
        settings.app_db_path,
        from_ts=from_ts,
        to_ts=to_ts,
        group_by=group_by,
    )
