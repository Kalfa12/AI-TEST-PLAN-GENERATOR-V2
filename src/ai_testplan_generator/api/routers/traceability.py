"""Traceability exploration endpoints (M09).

GET /trace/{artefact_id}                          full lineage
GET /trace/{artefact_id}/ancestors?depth=3        upstream ancestors
GET /projects/{project_id}/coverage               project coverage matrix
GET /projects/{project_id}/gaps                   uncovered requirements
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ai_testplan_generator.api.deps import get_brain, get_current_user, get_plans, get_project_plans
from ai_testplan_generator.api.errors import NotFoundError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.models import TestPlan
from ai_testplan_generator.pipelines.brain import Brain

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["traceability"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TraceNode(BaseModel):
    id: str
    type: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceEdge(BaseModel):
    source: str
    target: str
    kind: str
    confidence: float = 1.0


class LineageResponse(BaseModel):
    root: TraceNode
    edges: list[TraceEdge] = Field(default_factory=list)
    nodes: dict[str, TraceNode] = Field(default_factory=dict)


class AncestorsResponse(BaseModel):
    artefact_id: str
    ancestors: list[TraceNode] = Field(default_factory=list)


class GapsResponse(BaseModel):
    project_id: str
    uncovered_requirement_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_from_graph(node_id: str, brain: Brain) -> TraceNode:
    from ai_testplan_generator.memory.cross_document import InMemoryCrossDocumentGraph

    graph = brain.memory.graph
    if isinstance(graph, InMemoryCrossDocumentGraph):
        attrs = dict(graph._g.nodes.get(node_id, {}))
        node_type = attrs.pop("type", None)
        return TraceNode(id=node_id, type=node_type, attributes=attrs)
    return TraceNode(id=node_id)


def _node_exists(node_id: str, brain: Brain) -> bool:
    from ai_testplan_generator.memory.cross_document import InMemoryCrossDocumentGraph

    graph = brain.memory.graph
    if isinstance(graph, InMemoryCrossDocumentGraph):
        return node_id in graph._g
    return True  # Non-NetworkX graphs: assume existence


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/trace/{artefact_id}/ancestors",
    response_model=AncestorsResponse,
    summary="Upstream ancestors for an artefact",
    dependencies=[Depends(get_current_user)],
)
async def trace_ancestors(
    artefact_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    depth: Annotated[int, Query(ge=1, le=10)] = 3,
) -> AncestorsResponse:
    if not _node_exists(artefact_id, brain):
        raise NotFoundError(f"Artefact '{artefact_id}' not found in the traceability graph.")
    ancestor_ids = brain.memory.graph.ancestors(artefact_id, depth=depth)
    return AncestorsResponse(
        artefact_id=artefact_id,
        ancestors=[_node_from_graph(aid, brain) for aid in ancestor_ids],
    )


@router.get(
    "/trace/{artefact_id}",
    response_model=LineageResponse,
    summary="Full lineage for an artefact (ancestors + descendants)",
    dependencies=[Depends(get_current_user)],
)
async def trace_lineage(
    artefact_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    depth: Annotated[int, Query(ge=1, le=10)] = 3,
) -> LineageResponse:
    if not _node_exists(artefact_id, brain):
        raise NotFoundError(f"Artefact '{artefact_id}' not found.")

    root = _node_from_graph(artefact_id, brain)
    ancestor_ids = brain.memory.graph.ancestors(artefact_id, depth=depth)
    all_ids = {artefact_id, *ancestor_ids}

    edges: list[TraceEdge] = []
    nodes: dict[str, TraceNode] = {}

    from ai_testplan_generator.memory.cross_document import InMemoryCrossDocumentGraph

    graph = brain.memory.graph
    if isinstance(graph, InMemoryCrossDocumentGraph):
        for nid in all_ids:
            if nid != artefact_id:
                nodes[nid] = _node_from_graph(nid, brain)
        for u, v, data in graph._g.edges(data=True):
            if u in all_ids or v in all_ids:
                edges.append(
                    TraceEdge(
                        source=u, target=v,
                        kind=data.get("kind", ""),
                        confidence=float(data.get("confidence", 1.0)),
                    )
                )

    return LineageResponse(root=root, edges=edges, nodes=nodes)


@router.get(
    "/projects/{project_id}/coverage",
    response_model=dict[str, list[str]],
    summary="Full project coverage matrix (requirement → test cases)",
    dependencies=[Depends(require("project.read"))],
)
async def project_coverage(
    project_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> dict[str, list[str]]:
    reqs = await brain.memory.get_requirements_for_project(project_id)
    req_ids = [r.id for r in reqs]
    return brain.memory.graph.coverage_matrix(req_ids)


@router.get(
    "/projects/{project_id}/gaps",
    response_model=GapsResponse,
    summary="Requirements with zero covering test cases",
    dependencies=[Depends(require("project.read"))],
)
async def project_gaps(
    project_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> GapsResponse:
    reqs = await brain.memory.get_requirements_for_project(project_id)
    req_ids = [r.id for r in reqs]
    matrix = brain.memory.graph.coverage_matrix(req_ids)
    gaps = [rid for rid, tcs in matrix.items() if not tcs]
    return GapsResponse(project_id=project_id, uncovered_requirement_ids=gaps)
