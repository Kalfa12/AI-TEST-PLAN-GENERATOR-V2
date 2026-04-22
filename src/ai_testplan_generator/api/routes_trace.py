"""Routes: traceability exploration.

GET /trace/{artefact_id}  — returns upstream graph (ancestors)
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_testplan_generator.api.deps import get_brain
from ai_testplan_generator.pipelines.brain import Brain

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["traceability"])


# ---- response model -------------------------------------------------------

class AncestorNode(BaseModel):
    id: str
    type: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceResponse(BaseModel):
    artefact_id: str
    ancestors: list[AncestorNode] = Field(default_factory=list)


# ---- endpoint --------------------------------------------------------------

@router.get("/trace/{artefact_id}", response_model=TraceResponse)
async def trace_artefact(
    artefact_id: str,
    depth: int = 3,
    brain: Brain = Depends(get_brain),
) -> TraceResponse:
    """Return upstream ancestors for a given artefact (test case, requirement, chunk, etc.).

    This powers the "why does this test exist?" drill-down: starting from a
    TestCase, walk `derives_from` edges to reach the originating Requirements,
    Chunks, Sections, and Documents.
    """
    graph = brain.memory.graph

    # Check if the node exists in the graph.
    if artefact_id not in graph._g:
        raise HTTPException(
            status_code=404,
            detail=f"Artefact '{artefact_id}' not found in the traceability graph.",
        )

    ancestor_ids = graph.ancestors(artefact_id, depth=depth)
    ancestors: list[AncestorNode] = []
    for aid in ancestor_ids:
        node_data = dict(graph._g.nodes.get(aid, {}))
        node_type = node_data.pop("type", None)
        ancestors.append(AncestorNode(id=aid, type=node_type, attributes=node_data))

    return TraceResponse(artefact_id=artefact_id, ancestors=ancestors)
