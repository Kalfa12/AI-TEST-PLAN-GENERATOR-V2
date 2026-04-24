"""Local-filesystem blob store.

Writes blobs under a configurable root directory. presign_get returns None
because there is no HTTP layer to sign URLs for.

Configure:
    BLOB_STORE_BACKEND=local
    BLOB_STORE_LOCAL_ROOT=./data/blobs
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import structlog

_log = structlog.get_logger(__name__)

_CHUNK_SIZE = 64 * 1024  # 64 KB


class LocalFilesystemBlobStore:
    """Stores blobs as files under a root directory.

    The key is used as the relative path, with slashes creating subdirectories.
    """

    def __init__(self, *, root: str = "./data/blobs") -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        _log.info("local_blob_store_init", root=str(self._root))

    def _path(self, key: str) -> Path:
        p = self._root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        await asyncio.to_thread(path.write_bytes, data)
        uri = path.as_uri()
        _log.debug("blob_put", key=key, size=len(data), content_type=content_type)
        return uri

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        return await asyncio.to_thread(path.read_bytes)

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)

        def _read_chunks() -> list[bytes]:
            chunks: list[bytes] = []
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
            return chunks

        chunks = await asyncio.to_thread(_read_chunks)
        for chunk in chunks:
            yield chunk

    async def delete(self, key: str) -> None:
        path = self._root / key
        if path.exists():
            await asyncio.to_thread(path.unlink)
            _log.debug("blob_delete", key=key)

    async def presign_get(self, key: str, expires_s: int = 900) -> str | None:
        return None
