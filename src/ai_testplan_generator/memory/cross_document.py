"""Cross-document context: the traceability graph.

Vector search gets you "similar text"; it doesn't tell you
"this test covers this requirement derived from these chunks of these
two documents". That structural truth is a graph, not a vector space.

Nodes: Documents, Sections, Chunks, Requirements, TestCases, TestSteps.
Edges: `derives_from`, `covers`, `refines`, `contradicts`, `duplicates`.

Reference impl: NetworkX DiGraph (in-process). Swap in Neo4j / Memgraph
later by implementing the same surface.
"""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import Any

import networkx as nx

from ai_testplan_generator.models.traceability import TraceKind, TraceLink


class CrossDocumentGraph:
    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._lock = RLock()

    # -- node admin -----------------------------------------------------------

    def add_node(self, node_id: str, node_type: str, **attrs: Any) -> None:
        with self._lock:
            self._g.add_node(node_id, type=node_type, **attrs)

    def add_nodes(self, items: Iterable[tuple[str, str, dict[str, Any]]]) -> None:
        with self._lock:
            for node_id, node_type, attrs in items:
                self._g.add_node(node_id, type=node_type, **attrs)

    # -- edges ----------------------------------------------------------------

    def add_link(self, link: TraceLink) -> None:
        with self._lock:
            self._g.add_edge(
                link.source_id,
                link.target_id,
                key=link.id,
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
        with self._lock:
            if node_id not in self._g:
                return []
            view = self._g.out_edges if direction == "out" else self._g.in_edges
            out: list[tuple[str, dict[str, Any]]] = []
            for u, v, data in view(node_id, data=True):
                if kinds is not None and TraceKind(data["kind"]) not in kinds:
                    continue
                out.append((v if direction == "out" else u, data))
            return out

    def coverage_matrix(self, plan_requirement_ids: Iterable[str]) -> dict[str, list[str]]:
        """For each requirement, which test cases cover it? Walks `covers` edges in reverse."""
        matrix: dict[str, list[str]] = {r: [] for r in plan_requirement_ids}
        with self._lock:
            for req_id in matrix:
                if req_id not in self._g:
                    continue
                for u, _v, data in self._g.in_edges(req_id, data=True):
                    if data.get("kind") == TraceKind.COVERS.value:
                        matrix[req_id].append(u)
        return matrix

    def ancestors(self, node_id: str, *, depth: int = 3) -> list[str]:
        """All upstream sources within `depth` hops along `derives_from` edges."""
        with self._lock:
            if node_id not in self._g:
                return []
            visited: set[str] = set()
            frontier: set[str] = {node_id}
            for _ in range(depth):
                next_frontier: set[str] = set()
                for n in frontier:
                    for _u, v, data in self._g.out_edges(n, data=True):
                        if data.get("kind") == TraceKind.DERIVES_FROM.value and v not in visited:
                            next_frontier.add(v)
                            visited.add(v)
                frontier = next_frontier
                if not frontier:
                    break
            return list(visited)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return nx.readwrite.json_graph.node_link_data(self._g)
