"""ARQ task: ingest_document.

Fetches blob bytes, runs the ingestion pipeline, publishes progress events.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

_log = structlog.get_logger(__name__)

# Returned in result dict when a ValidationError is caught (no ARQ retry).
_VALIDATION_ERROR_TYPE = "ValidationError"


async def ingest_document(
    ctx: dict[str, Any],
    *,
    blob_key: str,
    project_id: str,
    scope: str,
    filename: str,
) -> dict[str, Any]:
    """Fetch blob from store, ingest into brain, return counts dict."""
    from pydantic import ValidationError as PydanticValidationError

    brain = ctx["brain"]
    blob_store = ctx["blob_store"]
    event_broker = ctx.get("event_broker")
    job_id: str = ctx.get("job_id", "unknown")
    job_try: int = ctx.get("job_try", 1)
    max_tries: int = ctx.get("max_tries", 4)

    topic = f"job:{job_id}"

    try:
        data: bytes = await blob_store.get(blob_key)
        ext = Path(filename).suffix.lower()

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        try:
            if scope == "general":
                result = await brain.general_kb.ingest(tmp_path, title=filename)
            else:
                kb = brain.project_kb(project_id)
                result = await kb.ingest(tmp_path, title=filename)
        finally:
            tmp_path.unlink(missing_ok=True)

        doc = result.document
        ingest_source_uri = doc.source_uri
        doc.source_uri = blob_key
        doc.metadata = {
            **doc.metadata,
            "blob_key": blob_key,
            "ingest_source_uri": ingest_source_uri,
            "original_filename": filename,
        }
        out: dict[str, Any] = {
            "document_id": doc.id,
            "n_sections": len(result.sections),
            "n_chunks": len(result.chunks),
            "n_requirements": len(result.requirements),
        }

        if event_broker is not None:
            await event_broker.publish(topic, {"kind": "ingest_done", **out})
            await event_broker.close_topic(topic)

        _log.info("arq_ingest_done", job_id=job_id, document_id=doc.id)
        return out

    except PydanticValidationError as exc:
        # Non-retryable — return error result so ARQ marks the job complete.
        if event_broker is not None:
            await event_broker.publish(topic, {"kind": "ingest_error", "error": str(exc)})
            await event_broker.close_topic(topic)
        _log.error("arq_ingest_validation_error", job_id=job_id, error=str(exc))
        return {
            "error": str(exc),
            "error_type": _VALIDATION_ERROR_TYPE,
            "success": False,
        }

    except Exception as exc:
        if event_broker is not None:
            await event_broker.publish(topic, {"kind": "ingest_error", "error": str(exc)})
            await event_broker.close_topic(topic)
        _log.error("arq_ingest_error", job_id=job_id, job_try=job_try, error=str(exc))

        # Write to dead-letter on final attempt.
        if job_try >= max_tries:
            redis = ctx.get("redis")
            if redis is not None:
                import time

                entry = json.dumps({
                    "job_id": job_id,
                    "task_name": "ingest_document",
                    "error": str(exc),
                    "kwargs": {
                        "blob_key": blob_key,
                        "project_id": project_id,
                        "scope": scope,
                        "filename": filename,
                    },
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                })
                await redis.zadd("jobs_deadletter", {entry: time.time()})

        raise
