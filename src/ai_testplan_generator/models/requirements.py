"""Testable requirements distilled from source documents."""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class RequirementKind(StrEnum):
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    SAFETY = "safety"
    RELIABILITY = "reliability"
    SECURITY = "security"
    REGULATORY = "regulatory"
    ENVIRONMENTAL = "environmental"
    INTERFACE = "interface"
    USABILITY = "usability"
    OPERATIONAL = "operational"


class Requirement(BaseModel):
    """An atomic, testable statement pulled from a source document.

    One requirement -> one-or-more TestCases. The `source_chunk_ids` field
    is the spine of traceability: every downstream artefact can be resolved
    back to the exact bytes in the original document.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:10]}")
    project_id: str | None = None
    external_id: str | None = None  # e.g. "SRS-4.2.1-a" if given in-doc
    kind: RequirementKind
    title: str
    statement: str  # the normative text, verbatim or minimally paraphrased
    rationale: str | None = None
    acceptance_hint: str | None = None  # free-text hint for the test architect
    priority: int = Field(ge=1, le=5, default=3)
    source_document_id: str
    source_section_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    verbatim_excerpt: str | None = None  # literal quote for audits
