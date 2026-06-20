"""SSE progress streaming + job status endpoints (M11 / M17).

GET /sessions/{session_id}/events   SSE stream of agent events
GET /jobs/{job_id}                  Current job status snapshot
"""

from __future__ import annotations

import json
from typing import Annotated, Any, AsyncIterator

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai_testplan_generator.api.deps import (
    get_current_user,
    get_event_broker,
    get_job_queue,
    get_project_repo,
)
from ai_testplan_generator.api.security.projects import ensure_project_access
from ai_testplan_generator.api.jobs import Job
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.events.broker import EventBroker
from ai_testplan_generator.jobs.queue import JobQueueProtocol

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["events"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    id: str
    kind: str
    status: str
    session_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    # Populated for interactive runs that are awaiting user accept/reprompt.
    paused_at: str | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobStatusResponse":
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status.value,
            session_id=job.session_id,
            result=job.result,
            error=job.error,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
            paused_at=getattr(job, "paused_at", None),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}/events",
    summary="SSE stream of agent events for a session",
)
async def session_events(
    session_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    broker: Annotated[EventBroker, Depends(get_event_broker)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    project_id: str | None = None,
) -> StreamingResponse:
    """Server-Sent Events stream. Subscribe before starting the job for full coverage."""
    if project_id is not None or not current_user.is_admin:
        await ensure_project_access(
            project_id=project_id,
            current_user=current_user,
            project_repo=project_repo,
        )

    async def _generator() -> AsyncIterator[str]:
        async for event in broker.subscribe(f"session:{session_id}"):
            if await request.is_disconnected():
                break
            data = json.dumps(event)
            yield f"event: agent_progress\ndata: {data}\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get current job status",
)
async def get_job_status(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> JobStatusResponse:
    job = await job_queue.get_status(job_id)
    await ensure_project_access(
        project_id=job.project_id,
        current_user=current_user,
        project_repo=project_repo,
    )
    return JobStatusResponse.from_job(job)
