"""Request/response schemas for document ingestion endpoints (M06)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_testplan_generator.models import Document


class DocumentUploadResponse(BaseModel):
    document: Document
    n_sections: int
    n_chunks: int
    n_requirements: int


class DocumentUploadAccepted(BaseModel):
    job_id: str
    document_id: str | None = None
    message: str = "Document queued for ingestion."


class DocumentListItem(BaseModel):
    id: str
    title: str
    kind: str
    scope: str
    n_chunks: int = 0
    ingested_at: str = ""
    source_uri: str = ""


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
