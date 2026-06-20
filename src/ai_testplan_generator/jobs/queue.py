"""Job queue abstractions for M17.

JobQueueProtocol — structural protocol shared by production and test queues.
JobQueue         — ARQ / Redis-backed production implementation.
FakeJobQueue     — in-memory implementation for tests (no Redis required).
DeadLetterEntry  — payload stored in the jobs_deadletter Redis sorted set.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

import structlog

from ai_testplan_generator.api.jobs import Job, JobStatus
from ai_testplan_generator.domain.jobs import JobRepository

_log = structlog.get_logger(__name__)

# Sentinel value written into result dicts by tasks that catch ValidationError
# so get_status can map "succeeded with error" to FAILED.
_VALIDATION_ERROR_TYPE = "ValidationError"


@dataclass
class DeadLetterEntry:
    job_id: str
    task_name: str
    error: str
    failed_at: str
    kwargs: dict[str, Any]


@runtime_checkable
class JobQueueProtocol(Protocol):
    async def enqueue(self, task_name: str, **kwargs: Any) -> str: ...
    async def get_status(self, job_id: str) -> Job: ...
    async def get_dead_letter_entries(self) -> list[DeadLetterEntry]: ...
    async def requeue_dead_letter(self, job_id: str) -> str: ...


# ---------------------------------------------------------------------------
# Production — ARQ / Redis
# ---------------------------------------------------------------------------

class JobQueue:
    """ARQ-backed job queue for production use."""

    def __init__(self, redis_pool: Any, *, job_repo: JobRepository | None = None) -> None:
        # redis_pool: arq.connections.ArqRedis — typed as Any to avoid hard
        # import at module level so tests without arq installed still work.
        self._redis = redis_pool
        self._job_repo = job_repo

    async def enqueue(self, task_name: str, **kwargs: Any) -> str:
        arq_job = await self._redis.enqueue_job(task_name, **kwargs)
        if arq_job is None:
            raise RuntimeError(
                f"Failed to enqueue job '{task_name}' (possible deduplication clash)."
            )
        job_id: str = arq_job.job_id
        if self._job_repo is not None:
            job = Job(
                id=job_id,
                kind=task_name,
                session_id=kwargs.get("session_id"),
                project_id=kwargs.get("project_id"),
            )
            await self._job_repo.save_job(job, project_id=kwargs.get("project_id"))
        return job_id

    async def get_status(self, job_id: str) -> Job:
        from ai_testplan_generator.api.errors import NotFoundError

        # Import ARQ types lazily so the module is importable without arq.
        from arq.jobs import Job as ArqJob  # type: ignore[import-untyped]
        from arq.jobs import JobStatus as ArqStatus  # type: ignore[import-untyped]

        arq_job = ArqJob(job_id, self._redis)
        arq_status = await arq_job.status()

        if arq_status == ArqStatus.not_found:
            if self._job_repo is not None:
                stored = await self._job_repo.get_job(job_id)
                if stored is not None:
                    return stored
            raise NotFoundError(f"Job '{job_id}' not found.")

        now = datetime.now(timezone.utc)

        # Attempt to read richer metadata.
        info = None
        try:
            info = await arq_job.info()
        except Exception:
            pass

        created_at: datetime = now
        if info is not None:
            enqueue_time = getattr(info, "enqueue_time", None)
            if isinstance(enqueue_time, datetime):
                created_at = enqueue_time

        kind: str = getattr(info, "function", "") if info is not None else ""

        result: dict[str, Any] | None = None
        error: str | None = None
        status = JobStatus.QUEUED

        if arq_status == ArqStatus.in_progress:
            status = JobStatus.IN_PROGRESS
        elif arq_status == ArqStatus.complete:
            result_info = None
            try:
                result_info = await arq_job.result_info()
            except Exception:
                pass
            if result_info is not None:
                raw = result_info.result
                if result_info.success:
                    if isinstance(raw, dict) and raw.get("error_type") == _VALIDATION_ERROR_TYPE:
                        # Task returned a validation-error sentinel — treat as FAILED.
                        status = JobStatus.FAILED
                        error = str(raw.get("error", "ValidationError"))
                    else:
                        status = JobStatus.SUCCEEDED
                        result = raw if isinstance(raw, dict) else {}
                else:
                    status = JobStatus.FAILED
                    error = str(raw) if raw is not None else "Unknown error"
            else:
                status = JobStatus.SUCCEEDED
        # else: queued or deferred → QUEUED (already set)

        job = Job(
            id=job_id,
            kind=kind,
            status=status,
            result=result,
            error=error,
            created_at=created_at,
            updated_at=now,
        )
        if self._job_repo is not None:
            stored = await self._job_repo.get_job(job_id)
            if stored is not None:
                job.project_id = stored.project_id
                job.session_id = stored.session_id
            await self._job_repo.save_job(job)
        return job

    async def get_dead_letter_entries(self) -> list[DeadLetterEntry]:
        raw_entries: list[bytes] = await self._redis.zrange("jobs_deadletter", 0, -1)
        entries: list[DeadLetterEntry] = []
        for raw in raw_entries:
            try:
                data = json.loads(raw)
                entries.append(
                    DeadLetterEntry(
                        job_id=data.get("job_id", ""),
                        task_name=data.get("task_name", ""),
                        error=data.get("error", ""),
                        failed_at=data.get("failed_at", ""),
                        kwargs=data.get("kwargs", {}),
                    )
                )
            except Exception:
                pass
        return entries

    async def requeue_dead_letter(self, job_id: str) -> str:
        from ai_testplan_generator.api.errors import NotFoundError

        entries = await self.get_dead_letter_entries()
        target: DeadLetterEntry | None = None
        raw_target: bytes | None = None

        raw_entries: list[bytes] = await self._redis.zrange("jobs_deadletter", 0, -1)
        for raw in raw_entries:
            try:
                data = json.loads(raw)
                if data.get("job_id") == job_id:
                    target = DeadLetterEntry(
                        job_id=data.get("job_id", ""),
                        task_name=data.get("task_name", ""),
                        error=data.get("error", ""),
                        failed_at=data.get("failed_at", ""),
                        kwargs=data.get("kwargs", {}),
                    )
                    raw_target = raw
                    break
            except Exception:
                pass

        # Suppress unused variable warning — entries not used after refactor.
        _ = entries

        if target is None or raw_target is None:
            raise NotFoundError(f"Dead-letter job '{job_id}' not found.")

        new_job_id = await self.enqueue(target.task_name, **target.kwargs)

        # Remove from dead-letter set.
        await self._redis.zrem("jobs_deadletter", raw_target)

        _log.info("dead_letter_requeued", old_job_id=job_id, new_job_id=new_job_id)
        return new_job_id


# ---------------------------------------------------------------------------
# Test double — in-process, no Redis
# ---------------------------------------------------------------------------

class FakeJobQueue:
    """In-memory job queue for tests.

    Fires the actual ARQ task function via asyncio.create_task so that
    test scenarios which complete synchronously (e.g. successful ingest of
    small blobs) can observe the result without requiring Redis.
    """

    def __init__(
        self,
        *,
        brain: Any,
        blob_store: Any,
        event_broker: Any,
        plans: dict[str, Any],
        project_plans: dict[str, list[str]],
        defects: dict[str, Any] | None = None,
        job_repo: JobRepository | None = None,
    ) -> None:
        self._jobs: dict[str, Job] = {}
        self._job_repo = job_repo
        self._ctx: dict[str, Any] = {
            "brain": brain,
            "blob_store": blob_store,
            "event_broker": event_broker,
            "plans": plans,
            "project_plans": project_plans,
            "defects": defects if defects is not None else {},
            "job_repo": job_repo,
            "max_tries": 4,
        }

    async def enqueue(self, task_name: str, **kwargs: Any) -> str:
        from ai_testplan_generator.jobs.tasks.autonomous import (
            delete_project_artefacts,
            run_autonomous,
            run_autonomous_interactive,
        )
        from ai_testplan_generator.jobs.tasks.ingest import ingest_document

        task_map: dict[str, Any] = {
            "ingest_document": ingest_document,
            "run_autonomous": run_autonomous,
            "run_autonomous_interactive": run_autonomous_interactive,
            "delete_project_artefacts": delete_project_artefacts,
        }

        job = Job(
            kind=task_name,
            session_id=kwargs.get("session_id"),
            project_id=kwargs.get("project_id"),
        )
        self._jobs[job.id] = job
        if self._job_repo is not None:
            await self._job_repo.save_job(job, project_id=kwargs.get("project_id"))

        fn = task_map.get(task_name)
        if fn is not None:
            ctx = {
                **self._ctx,
                "job_id": job.id,
                "job_try": 1,
                # Interactive runs need the live Job objects to signal
                # pause/resume; expose the registry through ctx.
                "jobs_index": self._jobs,
            }
            asyncio.create_task(self._run(job, fn, ctx, kwargs))

        return job.id

    async def _run(
        self,
        job: Job,
        fn: Any,
        ctx: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> None:
        job.start()
        if self._job_repo is not None:
            await self._job_repo.save_job(job, project_id=kwargs.get("project_id"))
        try:
            result = await fn(ctx, **kwargs)
            if isinstance(result, dict) and result.get("success") is False:
                job.fail(str(result.get("error", "task returned failure")))
            else:
                job.succeed(result if isinstance(result, dict) else {})
            if self._job_repo is not None:
                await self._job_repo.delete_checkpoint(job.id)
                await self._job_repo.save_job(job, project_id=kwargs.get("project_id"))
        except Exception as exc:
            job.fail(str(exc))
            if self._job_repo is not None:
                await self._job_repo.delete_checkpoint(job.id)
                await self._job_repo.save_job(job, project_id=kwargs.get("project_id"))

    async def get_status(self, job_id: str) -> Job:
        from ai_testplan_generator.api.errors import NotFoundError

        job = self._jobs.get(job_id)
        if job is None:
            if self._job_repo is not None:
                stored = await self._job_repo.get_job(job_id)
                if stored is not None:
                    return stored
            raise NotFoundError(f"Job '{job_id}' not found.")
        return job

    async def get_dead_letter_entries(self) -> list[DeadLetterEntry]:
        return []

    async def requeue_dead_letter(self, job_id: str) -> str:
        from ai_testplan_generator.api.errors import NotFoundError

        raise NotFoundError(f"Dead-letter job '{job_id}' not found (no Redis in tests).")
