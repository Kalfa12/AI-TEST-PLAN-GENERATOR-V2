"""Tests for LocalFilesystemBlobStore (M04)."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


@pytest.fixture
def store(tmp_path: Path) -> LocalFilesystemBlobStore:
    return LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))


class TestLocalFilesystemBlobStore:
    async def test_put_and_get_roundtrip(self, store: LocalFilesystemBlobStore) -> None:
        data = b"hello, blob world"
        key = "projects/proj-1/docs/abc123/file.txt"
        uri = await store.put(key, data, "text/plain")
        assert uri.startswith("file://")
        retrieved = await store.get(key)
        assert retrieved == data

    async def test_put_returns_canonical_uri(self, store: LocalFilesystemBlobStore) -> None:
        key = "projects/proj-1/docs/sha256abc/report.pdf"
        uri = await store.put(key, b"pdf content", "application/pdf")
        assert "report.pdf" in uri

    async def test_delete(self, store: LocalFilesystemBlobStore) -> None:
        key = "projects/proj-1/docs/del/file.bin"
        await store.put(key, b"to delete", "application/octet-stream")
        await store.delete(key)
        with pytest.raises(FileNotFoundError):
            await store.get(key)

    async def test_delete_nonexistent_is_noop(self, store: LocalFilesystemBlobStore) -> None:
        await store.delete("does/not/exist.bin")

    async def test_presign_returns_none(self, store: LocalFilesystemBlobStore) -> None:
        result = await store.presign_get("any/key.pdf")
        assert result is None

    async def test_get_stream(self, store: LocalFilesystemBlobStore) -> None:
        data = b"stream content " * 1000
        key = "projects/proj-1/docs/stream/big.bin"
        await store.put(key, data, "application/octet-stream")
        chunks: list[bytes] = []
        async for chunk in store.get_stream(key):
            chunks.append(chunk)
        assert b"".join(chunks) == data

    async def test_large_blob_integrity(self, store: LocalFilesystemBlobStore) -> None:
        data = b"X" * (2 * 1024 * 1024)  # 2 MB
        sha = hashlib.sha256(data).hexdigest()
        key = f"projects/proj-1/docs/{sha}/large.bin"
        await store.put(key, data, "application/octet-stream")
        retrieved = await store.get(key)
        assert hashlib.sha256(retrieved).hexdigest() == sha

    async def test_key_convention_creates_subdirs(
        self, store: LocalFilesystemBlobStore, tmp_path: Path
    ) -> None:
        key = "projects/proj-42/docs/deadbeef/spec.docx"
        await store.put(key, b"content", "application/vnd.openxmlformats")
        expected = tmp_path / "blobs" / "projects" / "proj-42" / "docs" / "deadbeef" / "spec.docx"
        assert expected.exists()
