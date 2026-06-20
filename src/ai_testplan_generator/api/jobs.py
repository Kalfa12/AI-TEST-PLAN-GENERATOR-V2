"""In-process job state registry.

Tracks background asyncio tasks (ingest, autonomous plan runs).
# TODO: replace with ARQ/Redis job queue (M17).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class JobStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"  # interactive run: waiting for user accept/reprompt
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Job:
    id: str = field(default_factory=lambda: f"job_{uuid4().hex[:10]}")
    kind: str = ""
    status: JobStatus = JobStatus.QUEUED
    session_id: str | None = None
    project_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Interactive-mode bookkeeping. Runtime-only — never serialised to ARQ.
    # `paused_at` is the agent name we just finished and are awaiting feedback for.
    paused_at: str | None = None
    paused_state: Any | None = None  # AutonomousState — typed Any to avoid import cycle
    # asyncio.Event the run task waits on after each checkpoint. Reset/set
    # by the resume endpoint.
    resume_signal: Any | None = None

    def start(self) -> None:
        self.status = JobStatus.IN_PROGRESS
        self.updated_at = datetime.now(timezone.utc)

    def pause(self, *, agent: str, state: Any) -> None:
        self.status = JobStatus.PAUSED
        self.paused_at = agent
        self.paused_state = state
        self.updated_at = datetime.now(timezone.utc)

    def resume(self) -> None:
        self.status = JobStatus.IN_PROGRESS
        self.paused_at = None
        self.updated_at = datetime.now(timezone.utc)

    def succeed(self, result: dict[str, Any]) -> None:
        self.status = JobStatus.SUCCEEDED
        self.result = result
        self.paused_at = None
        self.paused_state = None
        self.updated_at = datetime.now(timezone.utc)

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.paused_at = None
        self.paused_state = None
        self.updated_at = datetime.now(timezone.utc)
