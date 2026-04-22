"""Routes: document ingestion.

POST /projects/{project_id}/ingest  — multipart file upload
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ai_testplan_generator.api.deps import get_brain
from ai_testplan_generator.models import Chunk, Document, Requirement, Section
from ai_testplan_generator.pipelines.brain import Brain

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["ingestion"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".md", ".txt"}


# ---- response model -------------------------------------------------------

class IngestionResponse(BaseModel):
    """Wire-format for a successful ingestion."""
    document: Document
    sections: list[Section] = Field(default_factory=list)
    chunks_count: int = 0
    requirements: list[Requirement] = Field(default_factory=list)


# ---- endpoint --------------------------------------------------------------

@router.post("/projects/{project_id}/ingest", response_model=IngestionResponse)
async def ingest_document(
    project_id: str,
    file: UploadFile,
    brain: Brain = Depends(get_brain),
) -> IngestionResponse:
    """Upload a document and ingest it into the project knowledge base.

    Accepted formats: .pdf, .docx, .xlsx, .xlsm, .md, .txt
    """
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()

    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # Stream to a temp file so loaders can work with a real path.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        kb = brain.project_kb(project_id)
        result = await kb.ingest(tmp_path, title=filename)
        _log.info(
            "api_ingest_done",
            project_id=project_id,
            document_id=result.document.id,
            n_chunks=len(result.chunks),
            n_reqs=len(result.requirements),
        )
        return IngestionResponse(
            document=result.document,
            sections=result.sections,
            chunks_count=len(result.chunks),
            requirements=result.requirements,
        )
    except Exception as exc:
        _log.error("api_ingest_error", project_id=project_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
