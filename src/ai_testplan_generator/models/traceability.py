"""Traceability links: the audit spine of the whole system.

Every downstream artefact (requirement, test case, test step) carries
TraceLinks back to (chunk, section, document). The graph is bidirectional
so we can answer both "what tests cover REQ-X?" and "which doc lines
spawned TC-Y?".
"""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TraceKind(StrEnum):
    DERIVES_FROM = "derives_from"  # artefact -> source chunk / requirement
    COVERS = "covers"  # test -> requirement
    REFINES = "refines"  # child requirement -> parent
    CONTRADICTS = "contradicts"  # flagged by reviewer
    DUPLICATES = "duplicates"  # dedup hints


class TraceLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"tr_{uuid4().hex[:10]}")
    kind: TraceKind
    source_id: str  # e.g. tc_xxx
    source_type: str  # e.g. "TestCase"
    target_id: str  # e.g. req_xxx / ch_xxx
    target_type: str  # e.g. "Requirement" / "Chunk"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    rationale: str | None = None
