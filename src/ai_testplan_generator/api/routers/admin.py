"""Admin endpoints (M19).

GET  /admin/jobs/deadletter                  list permanently-failed jobs (admin only)
POST /admin/jobs/deadletter/{job_id}/requeue re-enqueue a dead-letter job (admin only)

All routes require the caller to be an admin (``user.is_admin == True``).
Redis-dependent behaviour is gracefully absent when Redis is unavailable.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_testplan_generator.api.deps import get_current_user, get_job_queue
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
    kwargs: dict[str, Any]


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
            kwargs=e.kwargs,
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
