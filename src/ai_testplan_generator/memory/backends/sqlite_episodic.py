"""SQLite-backed episodic memory store (async via aiosqlite).

Implements the `EpisodicStore` protocol. Schema is initialised from the
migration file `migrations/001_episodic.sql` on first connection.

Install: pip install aiosqlite  (included in core deps)

Configure:
    EPISODIC_MEMORY_BACKEND=sqlite
    SQLITE_EPISODIC_PATH=data/episodic.db
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from ai_testplan_generator.memory.base import EpisodeEvent

_log = structlog.get_logger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

try:
    import aiosqlite
except ImportError as exc:
    raise ImportError(
        "aiosqlite is required for the SQLite episodic backend. "
        "Install it with: pip install aiosqlite"
    ) from exc


class SqliteEpisodicStore:
    """Async episodic store backed by SQLite via aiosqlite.

    Each event is a row in `episodic_events`. Concurrent asyncio tasks may
    write simultaneously; WAL mode keeps reads non-blocking during writes.
    """

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, *, db_path: str) -> "SqliteEpisodicStore":
        store = cls(db_path=db_path)
        await store._init()
        return store

    async def _init(self) -> None:
        path = Path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(path))
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._run_migrations()
        await self._conn.commit()
        _log.info("sqlite_episodic_init", path=str(path))

    async def _run_migrations(self) -> None:
        assert self._conn is not None
        for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            sql = sql_file.read_text()
            await self._conn.executescript(sql)

    def _connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteEpisodicStore not initialised — call create() first")
        return self._conn

    async def append(self, event: EpisodeEvent) -> None:
        ts = event.ts or datetime.now(timezone.utc)
        await self._connection().execute(
            """INSERT INTO episodic_events (ts, session_id, actor, kind, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                ts.isoformat(),
                event.session_id,
                event.actor,
                event.kind,
                event.content,
                json.dumps(event.metadata),
            ),
        )
        await self._connection().commit()

    async def recent(
        self,
        session_id: str,
        *,
        limit: int = 50,
        kinds: Sequence[str] | None = None,
    ) -> list[EpisodeEvent]:
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            sql = f"""
                SELECT ts, session_id, actor, kind, content, metadata
                FROM episodic_events
                WHERE session_id = ? AND kind IN ({placeholders})
                ORDER BY id DESC
                LIMIT ?
            """
            params: tuple[Any, ...] = (session_id, *kinds, limit)
        else:
            sql = """
                SELECT ts, session_id, actor, kind, content, metadata
                FROM episodic_events
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            """
            params = (session_id, limit)

        async with self._connection().execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        rows.reverse()
        return [_row_to_event(r) for r in rows]

    async def search(self, session_id: str, query: str, *, limit: int = 20) -> list[EpisodeEvent]:
        sql = """
            SELECT ts, session_id, actor, kind, content, metadata
            FROM episodic_events
            WHERE session_id = ? AND content LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """
        async with self._connection().execute(sql, (session_id, f"%{query}%", limit)) as cursor:
            rows = await cursor.fetchall()
        rows.reverse()
        return [_row_to_event(r) for r in rows]

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def _row_to_event(row: tuple[str, str, str, str, str, str]) -> EpisodeEvent:
    ts_str, session_id, actor, kind, content, metadata_json = row
    return EpisodeEvent(
        ts=datetime.fromisoformat(ts_str),
        session_id=session_id,
        actor=actor,
        kind=kind,
        content=content,
        metadata=json.loads(metadata_json),
    )
