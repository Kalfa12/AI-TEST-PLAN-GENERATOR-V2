"""Document ingestion endpoints (M06).

POST   /projects/{project_id}/documents          upload + ingest
GET    /projects/{project_id}/documents          list with pagination
GET    /projects/{project_id}/documents/{doc_id} single doc metadata
GET    /projects/{project_id}/documents/{doc_id}/download presigned/stream
DELETE /projects/{project_id}/documents/{doc_id} remove doc
POST   /general/documents                        upload to general KB
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import StreamingResponse

from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_job_queue,
    get_settings,
)
from ai_testplan_generator.api.errors import NotFoundError, ValidationError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.api.schemas.documents import (
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadAccepted,
    DocumentUploadResponse,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.jobs.queue import JobQueueProtocol
from ai_testplan_generator.models import Document
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["documents"])

_ALLOWED_EXT = {".pdf", ".docx", ".xlsx", ".xlsm", ".md", ".txt"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _safe_filename(filename: str) -> str:
    return Path(filename).name or "upload"


def _attach_blob_metadata(doc: Document, *, blob_key: str, filename: str) -> Document:
    ingest_source_uri = doc.source_uri
    doc.source_uri = blob_key
    doc.metadata = {
        **doc.metadata,
        "blob_key": blob_key,
        "ingest_source_uri": ingest_source_uri,
        "original_filename": filename,
    }
    return doc


def _blob_key_for_document(doc: Document) -> str:
    return doc.metadata.get("blob_key") or doc.source_uri


def _document_list_item(d: Document, n_chunks: int) -> DocumentListItem:
    return DocumentListItem(
        id=d.id,
        title=d.title,
        kind=d.kind.value,
        scope=d.scope,
        n_chunks=n_chunks,
        ingested_at=d.ingested_at.isoformat(),
        source_uri=d.source_uri,
    )


async def _stream_to_blob(
    file: UploadFile,
    blob_store: BlobStore,
    *,
    project_id: str,
    scope: str,  # noqa: ARG001
) -> tuple[str, bytes, str]:
    """Read UploadFile in chunks, compute sha256, and store in blob store.

    Returns (blob_key, full_data, sha256_hex).
    """
    filename = _safe_filename(file.filename or "upload")
    sha = hashlib.sha256()
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(1 << 20)  # 1 MB
        if not chunk:
            break
        sha.update(chunk)
        chunks.append(chunk)
    data = b"".join(chunks)
    sha256 = sha.hexdigest()
    key = f"projects/{project_id}/docs/{sha256}/{filename}"
    content_type = file.content_type or "application/octet-stream"
    await blob_store.put(key, data, content_type)
    return key, data, sha256


async def _ingest_from_bytes(
    brain: Brain,
    data: bytes,
    *,
    filename: str,
    project_id: str,
    scope: str,
    sha256: str,  # noqa: ARG001
    blob_uri: str,
) -> tuple[Document, int, int, int]:
    """Write data to a temp file, run ingest pipeline, return counts."""
    ext = _ext(filename)
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        if scope == "general":
            result = await brain.general_kb.ingest(tmp_path, title=filename)
        else:
            kb = brain.project_kb(project_id)
            result = await kb.ingest(tmp_path, title=filename)
        doc = _attach_blob_metadata(
            result.document,
            blob_key=blob_uri,
            filename=filename,
        )
        await brain.memory.register_document(doc)
        return doc, len(result.sections), len(result.chunks), len(result.requirements)
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Endpoints — project-scoped
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/documents",
    status_code=200,
    response_model=None,
    summary="Upload and ingest a document",
    dependencies=[Depends(require("document.upload"))],
)
async def upload_document(
    project_id: str,
    file: UploadFile,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> DocumentUploadResponse | DocumentUploadAccepted:
    filename = _safe_filename(file.filename or "upload")
    if _ext(filename) not in _ALLOWED_EXT:
        raise ValidationError(
            f"Unsupported file type '{_ext(filename)}'. "
            f"Accepted: {', '.join(sorted(_ALLOWED_EXT))}"
        )

    blob_key, data, sha256 = await _stream_to_blob(
        file, blob_store, project_id=project_id, scope="project"
    )

    if len(data) > settings.large_doc_threshold_bytes:
        job_id = await job_queue.enqueue(
            "ingest_document",
            blob_key=blob_key,
            project_id=project_id,
            scope="project",
            filename=filename,
        )
        return DocumentUploadAccepted(job_id=job_id)

    doc, n_sections, n_chunks, n_reqs = await _ingest_from_bytes(
        brain, data,
        filename=filename, project_id=project_id, scope="project",
        sha256=sha256, blob_uri=blob_key,
    )
    _log.info("ingest_done", project_id=project_id, doc_id=doc.id,
              n_chunks=n_chunks, n_reqs=n_reqs)
    return DocumentUploadResponse(
        document=doc, n_sections=n_sections, n_chunks=n_chunks, n_requirements=n_reqs
    )


@router.get(
    "/projects/{project_id}/documents",
    response_model=DocumentListResponse,
    summary="List documents for a project",
    dependencies=[Depends(require("document.read"))],
)
async def list_documents(
    project_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    docs = await brain.memory.get_documents_for_project(project_id)
    total = len(docs)
    page = docs[offset : offset + limit]
    items: list[DocumentListItem] = []
    for d in page:
        chunks = await brain.memory.get_chunks_for_document(d.id)
        items.append(_document_list_item(d, len(chunks)))
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}/documents/{doc_id}",
    response_model=Document,
    summary="Get document metadata",
    dependencies=[Depends(require("document.read"))],
)
async def get_document(
    project_id: str,
    doc_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> Document:
    docs = await brain.memory.get_documents_for_project(project_id)
    for d in docs:
        if d.id == doc_id:
            return d
    raise NotFoundError(f"Document '{doc_id}' not found in project '{project_id}'.")


@router.get(
    "/projects/{project_id}/documents/{doc_id}/download",
    summary="Download document bytes",
    dependencies=[Depends(require("document.read"))],
)
async def download_document(
    project_id: str,
    doc_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> StreamingResponse:
    docs = await brain.memory.get_documents_for_project(project_id)
    doc: Document | None = None
    for d in docs:
        if d.id == doc_id:
            doc = d
            break
    if doc is None:
        raise NotFoundError(f"Document '{doc_id}' not found.")

    blob_key = _blob_key_for_document(doc)
    presigned = await blob_store.presign_get(blob_key)
    if presigned:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=presigned)  # type: ignore[return-value]

    async def _stream() -> Any:
        async for chunk in await blob_store.get_stream(blob_key):
            yield chunk

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}"'},
    )


@router.delete(
    "/projects/{project_id}/documents/{doc_id}",
    status_code=204,
    summary="Delete a document and its derived artefacts",
    dependencies=[Depends(require("document.delete"))],
)
async def delete_document(
    project_id: str,
    doc_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> None:
    docs = await brain.memory.get_documents_for_project(project_id)
    doc: Document | None = None
    for d in docs:
        if d.id == doc_id:
            doc = d
            break
    if doc is None:
        raise NotFoundError(f"Document '{doc_id}' not found.")

    # Remove blob.
    try:
        await blob_store.delete(_blob_key_for_document(doc))
    except Exception:
        pass  # blob may already be gone

    await brain.memory.delete_document(doc_id)

    _log.info("doc_deleted", project_id=project_id, doc_id=doc_id)


# ---------------------------------------------------------------------------
# Endpoints — general KB
# ---------------------------------------------------------------------------

@router.post(
    "/general/documents",
    status_code=200,
    response_model=None,
    summary="Upload document to general (cross-project) knowledge base",
    dependencies=[Depends(require("general_kb.write"))],
)
async def upload_general_document(
    file: UploadFile,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    job_queue: Annotated[JobQueueProtocol, Depends(get_job_queue)],
) -> DocumentUploadResponse | DocumentUploadAccepted:
    filename = _safe_filename(file.filename or "upload")
    if _ext(filename) not in _ALLOWED_EXT:
        raise ValidationError(
            f"Unsupported file type '{_ext(filename)}'. "
            f"Accepted: {', '.join(sorted(_ALLOWED_EXT))}"
        )

    blob_key, data, sha256 = await _stream_to_blob(
        file, blob_store, project_id="general", scope="general"
    )

    if len(data) > settings.large_doc_threshold_bytes:
        job_id = await job_queue.enqueue(
            "ingest_document",
            blob_key=blob_key,
            project_id="general",
            scope="general",
            filename=filename,
        )
        return DocumentUploadAccepted(job_id=job_id)

    doc, n_sections, n_chunks, n_reqs = await _ingest_from_bytes(
        brain, data,
        filename=filename, project_id="general", scope="general",
        sha256=sha256, blob_uri=blob_key,
    )
    return DocumentUploadResponse(
        document=doc, n_sections=n_sections, n_chunks=n_chunks, n_requirements=n_reqs
    )


@router.get(
    "/general/documents",
    response_model=DocumentListResponse,
    summary="List documents in the general knowledge base",
    dependencies=[Depends(require("general_kb.read"))],
)
async def list_general_documents(
    brain: Annotated[Brain, Depends(get_brain)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    docs = [
        d
        for d in await brain.memory.get_documents_for_project(None)
        if d.scope == "general"
    ]
    total = len(docs)
    page = docs[offset : offset + limit]
    items: list[DocumentListItem] = []
    for d in page:
        chunks = await brain.memory.get_chunks_for_document(d.id)
        items.append(_document_list_item(d, len(chunks)))
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.delete(
    "/general/documents/{doc_id}",
    status_code=204,
    summary="Delete a general knowledge-base document",
    dependencies=[Depends(require("general_kb.write"))],
)
async def delete_general_document(
    doc_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> None:
    docs = [
        d
        for d in await brain.memory.get_documents_for_project(None)
        if d.scope == "general"
    ]
    doc = next((d for d in docs if d.id == doc_id), None)
    if doc is None:
        raise NotFoundError(f"General document '{doc_id}' not found.")
    try:
        await blob_store.delete(_blob_key_for_document(doc))
    except Exception:
        pass
    await brain.memory.delete_document(doc_id)
    _log.info("general_doc_deleted", doc_id=doc_id)
