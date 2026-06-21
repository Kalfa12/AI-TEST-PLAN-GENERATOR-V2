"""Durable job and checkpoint repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from ai_testplan_generator.api.jobs import Job, JobStatus

_log = structlog.get_logger(__name__)

_MIGRATION_ID = "job_store_v1"
_SQLITE_BUSY_TIMEOUT_MS = 30_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,
    session_id  TEXT,
    project_id  TEXT,
    result_json TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    paused_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS job_checkpoints (
    job_id         TEXT PRIMARY KEY,
    paused_at      TEXT NOT NULL,
    state_json     TEXT NOT NULL,
    directive_json TEXT,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_checkpoints_paused_at ON job_checkpoints(paused_at);
"""


@dataclass(frozen=True)
class JobCheckpoint:
    job_id: str
    paused_at: str
    state: dict[str, Any]
    directive: dict[str, Any] | None = None
    updated_at: datetime | None = None


class JobRepository:
    """Async SQLite-backed source of truth for job/checkpoint metadata."""

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, *, db_path: str) -> "JobRepository":
        repo = cls(db_path=db_path)
        await repo._init()
        return repo

    async def _init(self) -> None:
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path, timeout=30.0)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        await self._conn.executescript(_SCHEMA)
        await self._record_migration(_MIGRATION_ID)
        await self._conn.commit()
        _log.info("job_repo_init", db_path=self._db_path)

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("JobRepository not initialised - call create() first")
        return self._conn

    async def _record_migration(self, migration_id: str) -> None:
        await self._db().execute(
            "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (migration_id, datetime.now(timezone.utc).isoformat()),
        )

    async def save_job(self, job: Job, *, project_id: str | None = None) -> None:
        if project_id is None:
            async with self._db().execute(
                "SELECT project_id FROM jobs WHERE id = ?",
                (job.id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is not None:
                project_id = row[0]
        await self._db().execute(
            """
            INSERT OR REPLACE INTO jobs
                (id, kind, status, session_id, project_id, result_json, error,
                 created_at, updated_at, paused_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.kind,
                job.status.value,
                job.session_id,
                project_id,
                json.dumps(job.result) if job.result is not None else None,
                job.error,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
                job.paused_at,
            ),
        )
        await self._db().commit()

    async def get_job(self, job_id: str) -> Job | None:
        async with self._db().execute(
            """
            SELECT id, kind, status, session_id, project_id, result_json, error,
                   created_at, updated_at, paused_at
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        job = Job(
            id=row[0],
            kind=row[1],
            status=JobStatus(row[2]),
            session_id=row[3],
            project_id=row[4],
            result=json.loads(row[5]) if row[5] else None,
            error=row[6],
            created_at=datetime.fromisoformat(row[7]),
            updated_at=datetime.fromisoformat(row[8]),
        )
        job.paused_at = row[9]
        return job

    async def save_checkpoint(
        self,
        *,
        job: Job,
        paused_at: str,
        state: dict[str, Any],
        project_id: str | None = None,
    ) -> None:
        job.paused_at = paused_at
        await self.save_job(job, project_id=project_id)
        await self._db().execute(
            """
            INSERT OR REPLACE INTO job_checkpoints
                (job_id, paused_at, state_json, directive_json, updated_at)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (
                job.id,
                paused_at,
                json.dumps(state),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self._db().commit()

    async def get_checkpoint(self, job_id: str) -> JobCheckpoint | None:
        async with self._db().execute(
            """
            SELECT job_id, paused_at, state_json, directive_json, updated_at
            FROM job_checkpoints
            WHERE job_id = ?
            """,
            (job_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return JobCheckpoint(
            job_id=row[0],
            paused_at=row[1],
            state=json.loads(row[2]),
            directive=json.loads(row[3]) if row[3] else None,
            updated_at=datetime.fromisoformat(row[4]) if row[4] else None,
        )

    async def save_resume_directive(self, job_id: str, directive: dict[str, Any]) -> None:
        await self._db().execute(
            """
            UPDATE job_checkpoints
            SET directive_json = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (
                json.dumps(directive),
                datetime.now(timezone.utc).isoformat(),
                job_id,
            ),
        )
        await self._db().commit()

    async def delete_checkpoint(self, job_id: str) -> None:
        await self._db().execute(
            "DELETE FROM job_checkpoints WHERE job_id = ?",
            (job_id,),
        )
        await self._db().commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
