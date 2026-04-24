"""Tests for Neo4jCrossDocumentGraph (M03).

Skipped entirely when the neo4j package is not installed or when a local
Neo4j instance is unreachable.  Uses a test mixin shared with the in-memory
impl to ensure behavioural parity.
"""

from __future__ import annotations

import pytest

neo4j = pytest.importorskip("neo4j", reason="neo4j driver not installed")

from ai_testplan_generator.memory.backends.neo4j_graph import Neo4jCrossDocumentGraph  # noqa: E402
from ai_testplan_generator.models.traceability import TraceKind, TraceLink  # noqa: E402

_NEO4J_URI = "bolt://localhost:7687"
_NEO4J_USER = "neo4j"
_NEO4J_PASSWORD = "changeme"


def _make_link(src: str, tgt: str, kind: TraceKind = TraceKind.DERIVES_FROM) -> TraceLink:
    return TraceLink(
        kind=kind,
        source_id=src,
        source_type="Node",
        target_id=tgt,
        target_type="Node",
    )


@pytest.fixture
async def graph() -> Neo4jCrossDocumentGraph:
    try:
        g = Neo4jCrossDocumentGraph(
            uri=_NEO4J_URI, user=_NEO4J_USER, password=_NEO4J_PASSWORD
        )
    except Exception:
        pytest.skip("Neo4j not reachable")
    yield g
    await g.close()


class TestNeo4jCrossDocumentGraph:
    def test_add_node_and_neighbours(self, graph: Neo4jCrossDocumentGraph) -> None:
        graph.add_node("doc_neo_1", "Document", title="SRS")
        graph.add_node("req_neo_1", "Requirement", title="REQ-1")
        graph.add_link(_make_link("req_neo_1", "doc_neo_1"))
        nbrs = graph.neighbours("req_neo_1", direction="out")
        ids = [n for n, _ in nbrs]
        assert "doc_neo_1" in ids

    def test_coverage_matrix(self, graph: Neo4jCrossDocumentGraph) -> None:
        graph.add_node("req_neo_cm", "Requirement")
        graph.add_node("tc_neo_1", "TestCase")
        graph.add_node("tc_neo_2", "TestCase")
        graph.add_link(_make_link("tc_neo_1", "req_neo_cm", TraceKind.COVERS))
        graph.add_link(_make_link("tc_neo_2", "req_neo_cm", TraceKind.COVERS))
        matrix = graph.coverage_matrix(["req_neo_cm"])
        assert len(matrix["req_neo_cm"]) == 2

    def test_ancestors(self, graph: Neo4jCrossDocumentGraph) -> None:
        graph.add_node("tc_neo_a", "TestCase")
        graph.add_node("req_neo_a", "Requirement")
        graph.add_node("ch_neo_a", "Chunk")
        graph.add_link(_make_link("tc_neo_a", "req_neo_a"))
        graph.add_link(_make_link("req_neo_a", "ch_neo_a"))
        anc = graph.ancestors("tc_neo_a", depth=3)
        assert "req_neo_a" in anc
        assert "ch_neo_a" in anc

    def test_to_dict(self, graph: Neo4jCrossDocumentGraph) -> None:
        graph.add_node("node_dict_test", "Document")
        result = graph.to_dict()
        assert "nodes" in result
        assert "links" in result
