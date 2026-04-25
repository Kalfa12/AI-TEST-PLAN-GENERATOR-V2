"""Document ingestion endpoints (M06).

POST   /projects/{project_id}/documents          upload + ingest
GET    /projects/{project_id}/documents          list with pagination
GET    /projects/{project_id}/documents/{doc_id} single doc metadata
GET    /projects/{project_id}/documents/{doc_id}/download presigned/stream
DELETE /projects/{project_id}/documents/{doc_id} remove doc
POST   /general/documents                        upload to general KB
"""

from __future__ import annotations

import asyncio
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
    get_event_broker,
    get_jobs,
    get_settings,
)
from ai_testplan_generator.api.errors import NotFoundError, ValidationError
from ai_testplan_generator.api.jobs import Job, JobStatus
from ai_testplan_generator.api.schemas.documents import (
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadAccepted,
    DocumentUploadResponse,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
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


async def _stream_to_blob(
    file: UploadFile,
    blob_store: BlobStore,
    *,
    project_id: str,
    scope: str,
) -> tuple[str, bytes, str]:
    """Read UploadFile in chunks, compute sha256, and store in blob store.

    Returns (blob_key, full_data, sha256_hex).
    """
    filename = file.filename or "upload"
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
    sha256: str,
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
        doc = result.document
        return doc, len(result.sections), len(result.chunks), len(result.requirements)
    finally:
        tmp_path.unlink(missing_ok=True)


async def _background_ingest(
    job: Job,
    brain: Brain,
    broker: InMemoryEventBroker,
    data: bytes,
    *,
    filename: str,
    project_id: str,
    scope: str,
    sha256: str,
    blob_uri: str,
) -> None:
    job.start()
    topic = f"job:{job.id}"
    try:
        doc, n_sections, n_chunks, n_reqs = await _ingest_from_bytes(
            brain, data,
            filename=filename, project_id=project_id, scope=scope,
            sha256=sha256, blob_uri=blob_uri,
        )
        result: dict[str, Any] = {
            "document_id": doc.id,
            "n_sections": n_sections,
            "n_chunks": n_chunks,
            "n_requirements": n_reqs,
        }
        job.succeed(result)
        await broker.publish(topic, {"kind": "ingest_done", **result})
        _log.info("bg_ingest_done", job_id=job.id, document_id=doc.id)
    except Exception as exc:
        job.fail(str(exc))
        await broker.publish(topic, {"kind": "ingest_error", "error": str(exc)})
        _log.error("bg_ingest_error", job_id=job.id, error=str(exc))
    finally:
        await broker.close_topic(topic)


# ---------------------------------------------------------------------------
# Endpoints — project-scoped
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/documents",
    status_code=200,
    response_model=None,
    summary="Upload and ingest a document",
)
async def upload_document(
    project_id: str,
    file: UploadFile,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    jobs: Annotated[dict[str, Job], Depends(get_jobs)],
    broker: Annotated[InMemoryEventBroker, Depends(get_event_broker)],
) -> DocumentUploadResponse | DocumentUploadAccepted:
    filename = file.filename or "upload"
    if _ext(filename) not in _ALLOWED_EXT:
        raise ValidationError(
            f"Unsupported file type '{_ext(filename)}'. Accepted: {', '.join(sorted(_ALLOWED_EXT))}"
        )

    blob_key, data, sha256 = await _stream_to_blob(
        file, blob_store, project_id=project_id, scope="project"
    )

    if len(data) > settings.large_doc_threshold_bytes:
        job = Job(kind="ingest_document")
        jobs[job.id] = job
        asyncio.create_task(
            _background_ingest(
                job, brain, broker, data,
                filename=filename, project_id=project_id, scope="project",
                sha256=sha256, blob_uri=blob_key,
            )
        )
        return DocumentUploadAccepted(job_id=job.id)

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
        items.append(
            DocumentListItem(
                id=d.id,
                title=d.title,
                kind=d.kind.value,
                scope=d.scope,
                n_chunks=len(chunks),
                ingested_at=d.ingested_at.isoformat(),
                source_uri=d.source_uri,
            )
        )
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}/documents/{doc_id}",
    response_model=Document,
    summary="Get document metadata",
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

    presigned = await blob_store.presign_get(doc.source_uri)
    if presigned:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=presigned)  # type: ignore[return-value]

    async def _stream() -> Any:
        async for chunk in await blob_store.get_stream(doc.source_uri):
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
        await blob_store.delete(doc.source_uri)
    except Exception:
        pass  # blob may already be gone

    # Remove from in-memory stores.
    brain.memory._store.documents.pop(doc_id, None)  # type: ignore[attr-defined]
    chunks = list(brain.memory._store.chunks.values())  # type: ignore[attr-defined]
    for ch in chunks:
        if ch.document_id == doc_id:
            brain.memory._store.chunks.pop(ch.id, None)  # type: ignore[attr-defined]
    reqs = list(brain.memory._store.requirements.values())  # type: ignore[attr-defined]
    for req in reqs:
        if req.source_document_id == doc_id:
            brain.memory._store.requirements.pop(req.id, None)  # type: ignore[attr-defined]

    _log.info("doc_deleted", project_id=project_id, doc_id=doc_id)


# ---------------------------------------------------------------------------
# Endpoints — general KB
# ---------------------------------------------------------------------------

@router.post(
    "/general/documents",
    status_code=200,
    response_model=None,
    summary="Upload document to general (cross-project) knowledge base",
)
async def upload_general_document(
    file: UploadFile,
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    jobs: Annotated[dict[str, Job], Depends(get_jobs)],
    broker: Annotated[InMemoryEventBroker, Depends(get_event_broker)],
) -> DocumentUploadResponse | DocumentUploadAccepted:
    filename = file.filename or "upload"
    if _ext(filename) not in _ALLOWED_EXT:
        raise ValidationError(
            f"Unsupported file type '{_ext(filename)}'. Accepted: {', '.join(sorted(_ALLOWED_EXT))}"
        )

    blob_key, data, sha256 = await _stream_to_blob(
        file, blob_store, project_id="general", scope="general"
    )

    if len(data) > settings.large_doc_threshold_bytes:
        job = Job(kind="ingest_document")
        jobs[job.id] = job
        asyncio.create_task(
            _background_ingest(
                job, brain, broker, data,
                filename=filename, project_id="general", scope="general",
                sha256=sha256, blob_uri=blob_key,
            )
        )
        return DocumentUploadAccepted(job_id=job.id)

    doc, n_sections, n_chunks, n_reqs = await _ingest_from_bytes(
        brain, data,
        filename=filename, project_id="general", scope="general",
        sha256=sha256, blob_uri=blob_key,
    )
    return DocumentUploadResponse(
        document=doc, n_sections=n_sections, n_chunks=n_chunks, n_requirements=n_reqs
    )
