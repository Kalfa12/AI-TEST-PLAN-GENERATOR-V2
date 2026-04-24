"""Tests for QdrantSemanticStore (M01).

Uses qdrant-client's in-memory mode so no real Qdrant server is needed.
Skips if qdrant-client is not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qdrant_client", reason="qdrant-client not installed")

from qdrant_client import AsyncQdrantClient  # noqa: E402

from ai_testplan_generator.memory.backends.qdrant_store import QdrantSemanticStore  # noqa: E402


@pytest.fixture
async def store() -> QdrantSemanticStore:
    s = QdrantSemanticStore.__new__(QdrantSemanticStore)
    s._client = AsyncQdrantClient(":memory:")
    s._embedding_dim = 4
    s._prefix = "test"
    s._ensured = set()
    return s


class TestQdrantSemanticStore:
    async def test_upsert_and_query(self, store: QdrantSemanticStore) -> None:
        await store.upsert(
            ids=["v1", "v2"],
            vectors=[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            payloads=[{"text": "alpha"}, {"text": "beta"}],
            namespace="test",
        )
        results = await store.query([1.0, 0.0, 0.0, 0.0], namespace="test", top_k=1)
        assert len(results) == 1
        assert results[0].id == "v1"

    async def test_upsert_overwrite(self, store: QdrantSemanticStore) -> None:
        await store.upsert(
            ids=["v1"],
            vectors=[[1.0, 0.0, 0.0, 0.0]],
            payloads=[{"v": 1}],
            namespace="overwrite",
        )
        await store.upsert(
            ids=["v1"],
            vectors=[[0.0, 1.0, 0.0, 0.0]],
            payloads=[{"v": 2}],
            namespace="overwrite",
        )
        results = await store.query([0.0, 1.0, 0.0, 0.0], namespace="overwrite", top_k=1)
        assert results[0].payload["v"] == 2

    async def test_filter_isolation(self, store: QdrantSemanticStore) -> None:
        await store.upsert(
            ids=["p1a", "p1b", "p2a"],
            vectors=[[1.0, 0.0, 0.0, 0.0]] * 3,
            payloads=[
                {"project_id": "proj-1"},
                {"project_id": "proj-1"},
                {"project_id": "proj-2"},
            ],
            namespace="filter_test",
        )
        results = await store.query(
            [1.0, 0.0, 0.0, 0.0],
            namespace="filter_test",
            top_k=10,
            filters={"project_id": "proj-1"},
        )
        assert all(r.payload["project_id"] == "proj-1" for r in results)
        assert len(results) == 2

    async def test_delete_namespace(self, store: QdrantSemanticStore) -> None:
        await store.upsert(
            ids=["v1"],
            vectors=[[1.0, 0.0, 0.0, 0.0]],
            payloads=[{}],
            namespace="to_delete",
        )
        await store.delete_namespace("to_delete")
        results = await store.query([1.0, 0.0, 0.0, 0.0], namespace="to_delete", top_k=5)
        assert results == []

    async def test_empty_upsert_is_noop(self, store: QdrantSemanticStore) -> None:
        await store.upsert(ids=[], vectors=[], payloads=[], namespace="empty")
