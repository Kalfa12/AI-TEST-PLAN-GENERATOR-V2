"""Blob storage backends.

Factory function `build_blob_store` dispatches on `Settings.blob_store_backend`.
When `Settings.blob_encryption_key` is set the returned store is wrapped with
`EncryptedBlobStore` for transparent at-rest encryption (M16).
"""

from __future__ import annotations

from ai_testplan_generator.storage.base import BlobStore

__all__ = ["BlobStore", "build_blob_store"]


def build_blob_store(settings: "Settings") -> BlobStore:  # type: ignore[name-defined]
    from ai_testplan_generator.config import Settings as _Settings

    s: _Settings = settings  # type: ignore[assignment]
    if s.blob_store_backend == "s3":
        from ai_testplan_generator.storage.s3 import S3BlobStore

        inner: BlobStore = S3BlobStore(bucket=s.s3_bucket, region=s.s3_region)
    else:
        from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore

        inner = LocalFilesystemBlobStore(root=s.blob_store_local_root)

    if s.blob_encryption_key:
        from ai_testplan_generator.storage.encrypted import EncryptedBlobStore

        return EncryptedBlobStore(
            inner=inner,
            encryption_key=s.blob_encryption_key,
            kek_version=s.blob_kek_version,
        )

    return inner
