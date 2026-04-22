"""SQLite-backed episodic memory store.

Implements the `EpisodicStore` protocol with persistent storage via
aiosqlite (async SQLite). Each event is stored as a row with JSON
metadata, enabling full session history to survive process restarts.

Configure:
    EPISODIC_MEMORY_BACKEND=sqlite
    SQLITE_EPISODIC_PATH=./data/episodic.db   # optional, defaults to in-CWD
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import structlog

from ai_testplan_generator.memory.base import EpisodeEvent

_log = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    session_id TEXT   NOT NULL,
    actor     TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    metadata  TEXT    NOT NULL DEFAULT '{}',
    UNIQUE(session_id, ts, actor, kind, content)
);

CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_session_kind ON episodes(session_id, kind);
"""


class SQLiteEpisodicStore:
    """Persistent episodic store backed by SQLite.

    Uses synchronous sqlite3 wrapped in async methods (SQLite writes are
    fast enough that this doesn't block meaningfully; avoids the aiosqlite
    dependency). For high-throughput production, swap to aiosqlite or
    Postgres.
    """

    def __init__(self, *, db_path: str | Path = "data/episodic.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        _log.info("sqlite_episodic_init", path=str(self._db_path))

    async def append(self, event: EpisodeEvent) -> None:
        ts = event.ts or datetime.now(timezone.utc)
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO episodes (ts, session_id, actor, kind, content, metadata)
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
            self._conn.commit()
        except sqlite3.Error as exc:
            _log.error("sqlite_episodic_append_error", error=str(exc))

    async def recent(
        self,
        session_id: str,
        *,
        limit: int = 50,
        kinds: Sequence[str] | None = None,
    ) -> list[EpisodeEvent]:
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            query = f"""
                SELECT ts, session_id, actor, kind, content, metadata
                FROM episodes
                WHERE session_id = ? AND kind IN ({placeholders})
                ORDER BY id DESC
                LIMIT ?
            """
            params: tuple[str | int, ...] = (session_id, *kinds, limit)
        else:
            query = """
                SELECT ts, session_id, actor, kind, content, metadata
                FROM episodes
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            """
            params = (session_id, limit)

        rows = self._conn.execute(query, params).fetchall()
        # Reverse so oldest is first (natural chronological order).
        rows.reverse()
        return [self._row_to_event(r) for r in rows]

    async def search(
        self, session_id: str, query: str, *, limit: int = 20
    ) -> list[EpisodeEvent]:
        """Simple LIKE search on content. For production, use FTS5."""
        rows = self._conn.execute(
            """SELECT ts, session_id, actor, kind, content, metadata
               FROM episodes
               WHERE session_id = ? AND content LIKE ?
               ORDER BY id DESC
               LIMIT ?""",
            (session_id, f"%{query}%", limit),
        ).fetchall()
        rows.reverse()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
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

    def close(self) -> None:
        self._conn.close()
