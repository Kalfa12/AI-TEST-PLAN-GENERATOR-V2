"""Tests for the EncryptedBlobStore wrapper (M16)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from ai_testplan_generator.storage.encrypted import EncryptedBlobStore
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def local_store(tmp_path):  # type: ignore[no-untyped-def]
    return LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))


@pytest.fixture
def enc_store(local_store: LocalFilesystemBlobStore, fernet_key: str) -> EncryptedBlobStore:
    return EncryptedBlobStore(inner=local_store, encryption_key=fernet_key)


async def test_encrypted_round_trip(
    enc_store: EncryptedBlobStore,
    local_store: LocalFilesystemBlobStore,
) -> None:
    plaintext = b"Hello, secret world!"

    await enc_store.put("test/blob.bin", plaintext, "application/octet-stream")

    # Read back through the encrypted store — should decrypt correctly.
    recovered = await enc_store.get("test/blob.bin")
    assert recovered == plaintext


async def test_raw_file_is_not_plaintext(
    enc_store: EncryptedBlobStore,
    local_store: LocalFilesystemBlobStore,
) -> None:
    plaintext = b"super secret content"

    await enc_store.put("test/secret.bin", plaintext, "application/octet-stream")

    # Read the raw bytes from the underlying store using the versioned key.
    raw = await local_store.get("v1:test/secret.bin")

    # The raw bytes must differ from the plaintext.
    assert raw != plaintext
    # And must not contain the plaintext as a substring (Fernet adds overhead).
    assert plaintext not in raw


async def test_get_stream_round_trip(enc_store: EncryptedBlobStore) -> None:
    plaintext = b"streaming data"
    await enc_store.put("stream/blob.bin", plaintext, "application/octet-stream")

    chunks: list[bytes] = []
    async for chunk in enc_store.get_stream("stream/blob.bin"):
        chunks.append(chunk)

    assert b"".join(chunks) == plaintext


async def test_delete(
    enc_store: EncryptedBlobStore,
    local_store: LocalFilesystemBlobStore,
) -> None:
    await enc_store.put("del/blob.bin", b"data", "application/octet-stream")
    await enc_store.delete("del/blob.bin")

    with pytest.raises(Exception):
        await local_store.get("v1:del/blob.bin")


async def test_presign_returns_none(enc_store: EncryptedBlobStore) -> None:
    result = await enc_store.presign_get("any/key")
    assert result is None


async def test_different_keys_produce_different_ciphertext(tmp_path) -> None:  # type: ignore[no-untyped-def]
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    plaintext = b"same plaintext"

    store1 = EncryptedBlobStore(
        inner=LocalFilesystemBlobStore(root=str(tmp_path / "s1")),
        encryption_key=key1,
    )
    store2 = EncryptedBlobStore(
        inner=LocalFilesystemBlobStore(root=str(tmp_path / "s2")),
        encryption_key=key2,
    )

    await store1.put("f.bin", plaintext, "application/octet-stream")
    await store2.put("f.bin", plaintext, "application/octet-stream")

    raw1 = await LocalFilesystemBlobStore(root=str(tmp_path / "s1")).get("v1:f.bin")
    raw2 = await LocalFilesystemBlobStore(root=str(tmp_path / "s2")).get("v1:f.bin")

    assert raw1 != raw2
