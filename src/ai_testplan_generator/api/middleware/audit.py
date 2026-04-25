"""Audit logging middleware (M15).

Fires a non-blocking asyncio task after every POST/PATCH/DELETE response that
writes one row to the ``audit_events`` table. The response is never held up.

The middleware reads ``request.state.current_user`` if available (set by the
``get_current_user`` dependency in M13); falls back to ``None``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_log = structlog.get_logger(__name__)

_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    user_id      TEXT,
    project_id   TEXT,
    action       TEXT NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    status       INTEGER NOT NULL,
    ip           TEXT,
    user_agent   TEXT,
    metadata     TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_events(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON audit_events(action, ts);
"""

_MUTATING_METHODS = {"POST", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, db_path: str) -> None:
        super().__init__(app)
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _ensure_conn(self) -> aiosqlite.Connection:
        conn = self._conn
        if conn is None:
            conn = await aiosqlite.connect(self._db_path)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.executescript(_AUDIT_SCHEMA)
            await conn.commit()
            self._conn = conn
        return conn

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        if request.method in _MUTATING_METHODS:
            conn = await self._ensure_conn()
            asyncio.create_task(
                self._write_audit(request, response.status_code, conn)
            )

        return response

    async def _write_audit(
        self, request: Request, status_code: int, conn: aiosqlite.Connection
    ) -> None:
        try:
            user = getattr(request.state, "current_user", None)
            user_id: str | None = user.id if user is not None else None
            project_id: str | None = request.path_params.get("project_id")
            action = f"{request.method}:{request.url.path}"
            ip = request.client.host if request.client else None
            user_agent: str | None = request.headers.get("user-agent")
            metadata: dict[str, Any] = {}

            await conn.execute(
                "INSERT INTO audit_events"
                " (ts, user_id, project_id, action, status, ip, user_agent, metadata)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    user_id,
                    project_id,
                    action,
                    status_code,
                    ip,
                    user_agent,
                    json.dumps(metadata),
                ),
            )
            await conn.commit()
        except Exception as exc:
            _log.warning("audit_write_failed", error=str(exc))
