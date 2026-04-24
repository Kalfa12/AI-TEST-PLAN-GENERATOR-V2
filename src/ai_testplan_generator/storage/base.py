"""BlobStore protocol — the public contract every storage backend must satisfy."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class BlobStore(Protocol):
    """Store and retrieve opaque binary blobs identified by a string key.

    Key convention:  projects/{project_id}/docs/{sha256}/{filename}

    `put` returns the canonical URI that callers should persist as
    `Document.source_uri`. For local storage that is a `file://` URI;
    for S3 it is an `s3://` URI.
    """

    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def get_stream(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def presign_get(self, key: str, expires_s: int = 900) -> str | None: ...
