"""Document / section / chunk models.

A Document is the raw source (spec, norm, requirement sheet, ...).
A Section is a hierarchical heading-bounded slice (preserves the table of
contents). A Chunk is the retrieval-sized unit actually embedded and fed to
the LLM. Chunks keep back-pointers to their Section and Document so every
test case can trace itself back to an exact location.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    MARKDOWN = "markdown"
    TEXT = "text"
    UNKNOWN = "unknown"


class ChunkKind(StrEnum):
    PROSE = "prose"
    HEADING = "heading"
    TABLE = "table"
    LIST = "list"
    FIGURE_CAPTION = "figure_caption"
    CODE = "code"
    FORMULA = "formula"


class Section(BaseModel):
    """Hierarchical section of a document (preserves the ToC)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _uid("sec"))
    document_id: str
    number: str | None = None  # e.g. "4.2.1"
    title: str
    level: int = Field(ge=1, le=10)
    parent_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    char_start: int
    char_end: int


class Chunk(BaseModel):
    """Retrieval-sized unit. Always back-pointed to its source."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _uid("ch"))
    document_id: str
    section_id: str | None = None
    kind: ChunkKind = ChunkKind.PROSE
    text: str
    token_count: int
    page_start: int | None = None
    page_end: int | None = None
    char_start: int
    char_end: int
    # Embedding is intentionally not stored on the chunk - it lives in the
    # semantic memory backend keyed by chunk.id, which keeps chunks cheap
    # to move around between agents.
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)


class Document(BaseModel):
    """Top-level ingested source."""

    id: str = Field(default_factory=lambda: _uid("doc"))
    project_id: str | None = None
    kind: DocumentKind
    title: str
    source_uri: str  # file://, s3://, https://, ...
    sha256: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    page_count: int | None = None
    language: str | None = None
    # Knowledge scope - drives retrieval partitioning.
    scope: Literal["general", "project"] = "project"
    metadata: dict[str, str] = Field(default_factory=dict)
