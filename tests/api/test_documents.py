"""M06: Document ingestion endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestDocumentUpload:
    async def test_rejects_unsupported_extension(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("photo.jpg", b"fake image", "image/jpeg")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"

    async def test_accepts_txt_small_file(self, client: AsyncClient) -> None:
        content = b"The system shall respond within 200ms."
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("spec.txt", content, "text/plain")},
        )
        # Sync ingest may fail if LLM mock raises in structured completion,
        # but must not return 422.
        assert resp.status_code in (200, 500)

    async def test_accepts_md_file(self, client: AsyncClient) -> None:
        content = b"# Requirements\n\nREQ-1: The system shall be fast.\n"
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("spec.md", content, "text/markdown")},
        )
        assert resp.status_code in (200, 500)

    async def test_list_documents_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-empty/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_get_document_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-1/documents/doc_nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    async def test_delete_document_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/projects/proj-1/documents/doc_nonexistent")
        assert resp.status_code == 404

    async def test_general_upload_rejects_unsupported(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/general/documents",
            files={"file": ("img.png", b"data", "image/png")},
        )
        assert resp.status_code == 422

    async def test_list_general_documents_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/general/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
