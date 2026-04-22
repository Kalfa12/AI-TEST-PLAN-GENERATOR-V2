"""Unit tests for the memory subsystem: semantic, episodic, working, cross-doc graph."""

import pytest
import pytest_asyncio

from ai_testplan_generator.memory.base import EpisodeEvent, SearchHit
from ai_testplan_generator.memory.cross_document import CrossDocumentGraph
from ai_testplan_generator.memory.episodic import InMemoryEpisodicStore
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.memory.semantic import InMemorySemanticStore
from ai_testplan_generator.memory.working import WorkingMemory
from ai_testplan_generator.models.traceability import TraceKind, TraceLink
from datetime import datetime, timezone

from tests.conftest import (
    MockLLMGateway,
    make_chunk,
    make_document,
    make_requirement,
    make_section,
    make_test_case,
)


# ---- Working Memory ---------------------------------------------------------

class TestWorkingMemory:
    def test_set_and_get(self):
        wm = WorkingMemory()
        wm.set("sess1", "key1", "value1")
        assert wm.get("sess1", "key1") == "value1"

    def test_get_missing_returns_none(self):
        wm = WorkingMemory()
        assert wm.get("sess1", "missing") is None

    def test_delete(self):
        wm = WorkingMemory()
        wm.set("sess1", "key1", "value1")
        wm.delete("sess1", "key1")
        assert wm.get("sess1", "key1") is None

    def test_clear(self):
        wm = WorkingMemory()
        wm.set("sess1", "a", 1)
        wm.set("sess1", "b", 2)
        wm.clear("sess1")
        assert wm.items("sess1") == {}

    def test_items(self):
        wm = WorkingMemory()
        wm.set("sess1", "x", 10)
        wm.set("sess1", "y", 20)
        assert wm.items("sess1") == {"x": 10, "y": 20}

    def test_session_isolation(self):
        wm = WorkingMemory()
        wm.set("sess1", "key", "a")
        wm.set("sess2", "key", "b")
        assert wm.get("sess1", "key") == "a"
        assert wm.get("sess2", "key") == "b"


# ---- Episodic Memory --------------------------------------------------------

class TestInMemoryEpisodicStore:
    @pytest.mark.asyncio
    async def test_append_and_recent(self):
        store = InMemoryEpisodicStore()
        event = EpisodeEvent(
            ts=datetime.now(timezone.utc),
            session_id="sess1",
            actor="user",
            kind="message",
            content="Hello",
        )
        await store.append(event)
        results = await store.recent("sess1")
        assert len(results) == 1
        assert results[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_recent_with_kind_filter(self):
        store = InMemoryEpisodicStore()
        for kind in ["message", "tool_call", "message", "decision"]:
            await store.append(
                EpisodeEvent(
                    ts=datetime.now(timezone.utc),
                    session_id="sess1",
                    actor="agent",
                    kind=kind,
                    content=f"Event of kind {kind}",
                )
            )
        msgs = await store.recent("sess1", kinds=["message"])
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_recent_limit(self):
        store = InMemoryEpisodicStore()
        for i in range(10):
            await store.append(
                EpisodeEvent(
                    ts=datetime.now(timezone.utc),
                    session_id="sess1",
                    actor="agent",
                    kind="message",
                    content=f"Event {i}",
                )
            )
        results = await store.recent("sess1", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search(self):
        store = InMemoryEpisodicStore()
        await store.append(
            EpisodeEvent(
                ts=datetime.now(timezone.utc),
                session_id="sess1",
                actor="user",
                kind="message",
                content="Find the performance requirement",
            )
        )
        results = await store.search("sess1", "performance")
        assert len(results) == 1


# ---- Semantic Memory ---------------------------------------------------------

class TestInMemorySemanticStore:
    @pytest.mark.asyncio
    async def test_upsert_and_query(self):
        store = InMemorySemanticStore()
        await store.upsert(
            ids=["v1", "v2"],
            vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            payloads=[{"text": "alpha"}, {"text": "beta"}],
            namespace="test",
        )
        results = await store.query([1.0, 0.0, 0.0], namespace="test", top_k=1)
        assert len(results) == 1
        assert results[0].id == "v1"

    @pytest.mark.asyncio
    async def test_query_with_filters(self):
        store = InMemorySemanticStore()
        await store.upsert(
            ids=["v1", "v2", "v3"],
            vectors=[[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
            payloads=[
                {"project": "A"},
                {"project": "B"},
                {"project": "A"},
            ],
            namespace="test",
        )
        results = await store.query(
            [1.0, 0.0], namespace="test", top_k=5, filters={"project": "A"}
        )
        assert all(r.payload["project"] == "A" for r in results)

    @pytest.mark.asyncio
    async def test_delete_namespace(self):
        store = InMemorySemanticStore()
        await store.upsert(
            ids=["v1"], vectors=[[1.0]], payloads=[{}], namespace="ns1"
        )
        await store.delete_namespace("ns1")
        results = await store.query([1.0], namespace="ns1")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self):
        store = InMemorySemanticStore()
        await store.upsert(
            ids=["v1"], vectors=[[1.0, 0.0]], payloads=[{"v": 1}], namespace="test"
        )
        await store.upsert(
            ids=["v1"], vectors=[[0.0, 1.0]], payloads=[{"v": 2}], namespace="test"
        )
        results = await store.query([0.0, 1.0], namespace="test", top_k=1)
        assert results[0].id == "v1"
        assert results[0].payload["v"] == 2


# ---- Cross-Document Graph ---------------------------------------------------

class TestCrossDocumentGraph:
    def test_add_node_and_neighbours(self):
        g = CrossDocumentGraph()
        g.add_node("doc_1", "Document", title="SRS")
        g.add_node("req_1", "Requirement", title="REQ-1")
        g.add_link(
            TraceLink(
                kind=TraceKind.DERIVES_FROM,
                source_id="req_1",
                source_type="Requirement",
                target_id="doc_1",
                target_type="Document",
            )
        )
        nbrs = g.neighbours("req_1", direction="out")
        assert len(nbrs) == 1
        assert nbrs[0][0] == "doc_1"

    def test_coverage_matrix(self):
        g = CrossDocumentGraph()
        g.add_node("req_1", "Requirement")
        g.add_node("tc_1", "TestCase")
        g.add_node("tc_2", "TestCase")
        g.add_link(
            TraceLink(
                kind=TraceKind.COVERS,
                source_id="tc_1",
                source_type="TestCase",
                target_id="req_1",
                target_type="Requirement",
            )
        )
        g.add_link(
            TraceLink(
                kind=TraceKind.COVERS,
                source_id="tc_2",
                source_type="TestCase",
                target_id="req_1",
                target_type="Requirement",
            )
        )
        matrix = g.coverage_matrix(["req_1"])
        assert len(matrix["req_1"]) == 2

    def test_ancestors(self):
        g = CrossDocumentGraph()
        g.add_node("tc_1", "TestCase")
        g.add_node("req_1", "Requirement")
        g.add_node("ch_1", "Chunk")
        g.add_node("doc_1", "Document")
        # tc_1 -> req_1 -> ch_1 -> doc_1 (all derives_from)
        for src, tgt in [("tc_1", "req_1"), ("req_1", "ch_1"), ("ch_1", "doc_1")]:
            g.add_link(
                TraceLink(
                    kind=TraceKind.DERIVES_FROM,
                    source_id=src,
                    source_type="Node",
                    target_id=tgt,
                    target_type="Node",
                )
            )
        anc = g.ancestors("tc_1", depth=5)
        assert "doc_1" in anc
        assert "req_1" in anc
        assert "ch_1" in anc

    def test_ancestors_unknown_node(self):
        g = CrossDocumentGraph()
        assert g.ancestors("nonexistent") == []


# ---- Memory Manager (integrated) --------------------------------------------

class TestMemoryManager:
    @pytest.mark.asyncio
    async def test_register_and_retrieve_document(self, brain):
        doc = make_document()
        await brain.memory.register_document(doc)
        docs = await brain.memory.get_documents_for_project("test-project")
        assert len(docs) == 1
        assert docs[0].id == doc.id

    @pytest.mark.asyncio
    async def test_register_chunks_with_embedding(self, brain):
        doc = make_document()
        sec = make_section(doc.id)
        chunks = [make_chunk(doc.id, sec.id, text=f"chunk {i}") for i in range(3)]
        await brain.memory.register_document(doc)
        await brain.memory.register_sections([sec])
        await brain.memory.register_chunks(chunks)
        # Verify chunks are stored.
        stored = await brain.memory.get_chunks_for_document(doc.id)
        assert len(stored) == 3
        # Verify embeddings were called.
        embed_calls = [c for c in brain.llm.call_log if c["method"] == "embed"]
        assert len(embed_calls) >= 1

    @pytest.mark.asyncio
    async def test_register_requirements(self, brain):
        doc = make_document()
        chunk = make_chunk(doc.id)
        req = make_requirement(source_chunk_ids=[chunk.id])
        await brain.memory.register_document(doc)
        await brain.memory.register_chunks([chunk])
        await brain.memory.register_requirements([req])
        reqs = await brain.memory.get_requirements_for_project("test-project")
        assert len(reqs) == 1

    @pytest.mark.asyncio
    async def test_hybrid_retrieval(self, brain):
        doc = make_document()
        chunk = make_chunk(doc.id, text="The pump shall not exceed 50 PSI")
        await brain.memory.register_document(doc)
        await brain.memory.register_chunks([chunk])
        bundle = await brain.memory.retrieve(
            "pressure limit", project_id="test-project"
        )
        # We at least get something back from semantic search.
        assert bundle is not None

    @pytest.mark.asyncio
    async def test_log_event(self, brain):
        await brain.memory.log_event(
            "sess-test", "user", "message", "Test message", key="value"
        )
        events = await brain.memory.episodic.recent("sess-test")
        assert len(events) == 1
        assert events[0].content == "Test message"
