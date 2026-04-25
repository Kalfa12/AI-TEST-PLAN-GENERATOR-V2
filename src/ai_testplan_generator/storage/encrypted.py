"""Envelope-encrypted blob store wrapper (M16).

Wraps any BlobStore implementation and applies Fernet symmetric encryption
on every put/get/get_stream call. The kek_version is stored as a prefix in
the blob key so future key rotation can be tracked:

    v1:{original_key}

To generate a key (must be a valid Fernet key — 32 random bytes, base64url):

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Configure:
    BLOB_ENCRYPTION_KEY=<base64url Fernet key>
    BLOB_KEK_VERSION=v1
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator

from cryptography.fernet import Fernet

from ai_testplan_generator.storage.base import BlobStore


class EncryptedBlobStore:
    """Wraps a BlobStore and transparently encrypts/decrypts blobs at rest."""

    def __init__(
        self,
        *,
        inner: BlobStore,
        encryption_key: str,
        kek_version: str = "v1",
    ) -> None:
        raw_key = base64.urlsafe_b64decode(encryption_key + "==")[:32]
        fernet_key = base64.urlsafe_b64encode(raw_key)
        self._fernet = Fernet(fernet_key)
        self._inner = inner
        self._kek_version = kek_version

    def _versioned_key(self, key: str) -> str:
        return f"{self._kek_version}:{key}"

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        encrypted = self._fernet.encrypt(data)
        return await self._inner.put(self._versioned_key(key), encrypted, content_type)

    async def get(self, key: str) -> bytes:
        encrypted = await self._inner.get(self._versioned_key(key))
        return self._fernet.decrypt(encrypted)

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        data = await self.get(key)
        yield data

    async def delete(self, key: str) -> None:
        await self._inner.delete(self._versioned_key(key))

    async def presign_get(self, key: str, expires_s: int = 900) -> str | None:
        return None
