"""Tests for SqliteEpisodicStore (M02).

Uses pytest's tmp_path fixture for an isolated DB file per test.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from ai_testplan_generator.memory.backends.sqlite_episodic import SqliteEpisodicStore
from ai_testplan_generator.memory.base import EpisodeEvent


def _event(session_id: str, kind: str = "message", content: str = "hello") -> EpisodeEvent:
    return EpisodeEvent(
        ts=datetime.now(timezone.utc),
        session_id=session_id,
        actor="user",
        kind=kind,
        content=content,
    )


@pytest.fixture
async def store(tmp_path: object) -> SqliteEpisodicStore:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = await SqliteEpisodicStore.create(db_path=db_path)
    yield s
    await s.close()


class TestSqliteEpisodicStore:
    async def test_append_and_recent(self, store: SqliteEpisodicStore) -> None:
        await store.append(_event("s1", content="First"))
        await store.append(_event("s1", content="Second"))
        results = await store.recent("s1")
        assert len(results) == 2
        assert results[0].content == "First"
        assert results[1].content == "Second"

    async def test_recent_session_isolation(self, store: SqliteEpisodicStore) -> None:
        await store.append(_event("s1", content="for-s1"))
        await store.append(_event("s2", content="for-s2"))
        s1 = await store.recent("s1")
        s2 = await store.recent("s2")
        assert len(s1) == 1 and s1[0].content == "for-s1"
        assert len(s2) == 1 and s2[0].content == "for-s2"

    async def test_recent_limit(self, store: SqliteEpisodicStore) -> None:
        for i in range(10):
            await store.append(_event("s1", content=f"msg {i}"))
        results = await store.recent("s1", limit=3)
        assert len(results) == 3

    async def test_kinds_filter(self, store: SqliteEpisodicStore) -> None:
        for kind in ["message", "tool_call", "message", "decision"]:
            await store.append(_event("s1", kind=kind, content=f"kind={kind}"))
        msgs = await store.recent("s1", kinds=["message"])
        assert len(msgs) == 2
        assert all(e.kind == "message" for e in msgs)

    async def test_search(self, store: SqliteEpisodicStore) -> None:
        await store.append(_event("s1", content="pump pressure limit exceeded"))
        await store.append(_event("s1", content="unrelated event"))
        hits = await store.search("s1", "pressure")
        assert len(hits) == 1
        assert "pressure" in hits[0].content

    async def test_1000_events_across_sessions(self, store: SqliteEpisodicStore) -> None:
        sessions = ["sa", "sb", "sc"]
        for i in range(1000):
            sess = sessions[i % 3]
            await store.append(_event(sess, content=f"event {i}"))
        for sess in sessions:
            results = await store.recent(sess, limit=500)
            assert len(results) > 0
            assert all(e.session_id == sess for e in results)

    async def test_concurrent_writes(self, store: SqliteEpisodicStore) -> None:
        async def _write(n: int) -> None:
            for i in range(10):
                await store.append(_event("concurrent", content=f"writer {n} event {i}"))

        await asyncio.gather(*[_write(i) for i in range(5)])
        results = await store.recent("concurrent", limit=1000)
        assert len(results) == 50
