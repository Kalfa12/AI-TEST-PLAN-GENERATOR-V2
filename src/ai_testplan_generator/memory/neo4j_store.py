"""Neo4j-backed cross-document traceability graph.

Drop-in replacement for `CrossDocumentGraph` (NetworkX), persisting the
full traceability graph in Neo4j. Cypher queries mirror the NetworkX API
surface: `add_node`, `add_link`, `neighbours`, `coverage_matrix`, `ancestors`.

Install: `pip install neo4j`

Configure:
    CROSSDOC_GRAPH_BACKEND=neo4j
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=changeme
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import structlog

from ai_testplan_generator.models.traceability import TraceKind, TraceLink

_log = structlog.get_logger(__name__)

try:
    from neo4j import GraphDatabase
except ImportError as exc:
    raise ImportError(
        "neo4j driver is required for the Neo4j backend. "
        "Install it with: pip install neo4j"
    ) from exc


class Neo4jGraphStore:
    """Persistent graph store backed by Neo4j.

    Mirrors the `CrossDocumentGraph` API so it can be used as a drop-in
    replacement via config wiring.
    """

    def __init__(
        self,
        *,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "changeme",
    ) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._ensure_indexes()
        _log.info("neo4j_graph_init", uri=uri)

    def _ensure_indexes(self) -> None:
        """Create indexes for efficient lookups."""
        with self._driver.session() as session:
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Node) ON (n.node_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Node) ON (n.node_type)")

    def close(self) -> None:
        self._driver.close()

    # -- node admin -----------------------------------------------------------

    def add_node(self, node_id: str, node_type: str, **attrs: Any) -> None:
        props = {"node_id": node_id, "node_type": node_type, **attrs}
        with self._driver.session() as session:
            session.run(
                """MERGE (n:Node {node_id: $node_id})
                   SET n += $props""",
                node_id=node_id,
                props=props,
            )

    def add_nodes(self, items: Iterable[tuple[str, str, dict[str, Any]]]) -> None:
        with self._driver.session() as session:
            for node_id, node_type, attrs in items:
                props = {"node_id": node_id, "node_type": node_type, **attrs}
                session.run(
                    """MERGE (n:Node {node_id: $node_id})
                       SET n += $props""",
                    node_id=node_id,
                    props=props,
                )

    # -- edges ----------------------------------------------------------------

    def add_link(self, link: TraceLink) -> None:
        with self._driver.session() as session:
            session.run(
                """MERGE (s:Node {node_id: $source_id})
                   MERGE (t:Node {node_id: $target_id})
                   MERGE (s)-[r:TRACE {link_id: $link_id}]->(t)
                   SET r.kind = $kind,
                       r.source_type = $source_type,
                       r.target_type = $target_type,
                       r.confidence = $confidence,
                       r.rationale = $rationale""",
                source_id=link.source_id,
                target_id=link.target_id,
                link_id=link.id,
                kind=link.kind.value,
                source_type=link.source_type,
                target_type=link.target_type,
                confidence=link.confidence,
                rationale=link.rationale,
            )

    def add_links(self, links: Iterable[TraceLink]) -> None:
        for link in links:
            self.add_link(link)

    # -- queries --------------------------------------------------------------

    def neighbours(
        self, node_id: str, *, kinds: set[TraceKind] | None = None, direction: str = "out"
    ) -> list[tuple[str, dict[str, Any]]]:
        if direction == "out":
            cypher = """
                MATCH (s:Node {node_id: $node_id})-[r:TRACE]->(t:Node)
                RETURN t.node_id AS neighbour, properties(r) AS data
            """
        else:
            cypher = """
                MATCH (t:Node)-[r:TRACE]->(s:Node {node_id: $node_id})
                RETURN t.node_id AS neighbour, properties(r) AS data
            """

        with self._driver.session() as session:
            result = session.run(cypher, node_id=node_id)
            out: list[tuple[str, dict[str, Any]]] = []
            for record in result:
                data = dict(record["data"])
                if kinds is not None and TraceKind(data.get("kind", "")) not in kinds:
                    continue
                out.append((record["neighbour"], data))
            return out

    def coverage_matrix(self, plan_requirement_ids: Iterable[str]) -> dict[str, list[str]]:
        """For each requirement, which test cases cover it?"""
        req_ids = list(plan_requirement_ids)
        matrix: dict[str, list[str]] = {r: [] for r in req_ids}

        with self._driver.session() as session:
            result = session.run(
                """UNWIND $req_ids AS rid
                   MATCH (tc:Node)-[r:TRACE {kind: 'covers'}]->(req:Node {node_id: rid})
                   RETURN req.node_id AS req_id, tc.node_id AS tc_id""",
                req_ids=req_ids,
            )
            for record in result:
                matrix[record["req_id"]].append(record["tc_id"])

        return matrix

    def ancestors(self, node_id: str, *, depth: int = 3) -> list[str]:
        """All upstream sources within `depth` hops along `derives_from` edges."""
        with self._driver.session() as session:
            result = session.run(
                """MATCH (start:Node {node_id: $node_id})
                         -[:TRACE *1..$depth {kind: 'derives_from'}]->(ancestor:Node)
                   RETURN DISTINCT ancestor.node_id AS aid""",
                node_id=node_id,
                depth=depth,
            )
            return [record["aid"] for record in result]

    def to_dict(self) -> dict[str, Any]:
        """Export the graph as a dict (for debugging / serialisation)."""
        with self._driver.session() as session:
            nodes_result = session.run(
                "MATCH (n:Node) RETURN n.node_id AS id, properties(n) AS props"
            )
            nodes = [{"id": r["id"], **r["props"]} for r in nodes_result]

            edges_result = session.run(
                """MATCH (s:Node)-[r:TRACE]->(t:Node)
                   RETURN s.node_id AS source, t.node_id AS target, properties(r) AS props"""
            )
            edges = [
                {"source": r["source"], "target": r["target"], **r["props"]}
                for r in edges_result
            ]

        return {"nodes": nodes, "links": edges}
