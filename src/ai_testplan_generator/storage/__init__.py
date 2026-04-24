"""Blob storage backends.

Factory function `build_blob_store` dispatches on `Settings.blob_store_backend`.
"""

from __future__ import annotations

from ai_testplan_generator.storage.base import BlobStore

__all__ = ["BlobStore", "build_blob_store"]


def build_blob_store(settings: "Settings") -> BlobStore:  # type: ignore[name-defined]
    from ai_testplan_generator.config import Settings as _Settings

    s: _Settings = settings  # type: ignore[assignment]
    if s.blob_store_backend == "s3":
        from ai_testplan_generator.storage.s3 import S3BlobStore

        return S3BlobStore(bucket=s.s3_bucket, region=s.s3_region)
    from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore

    return LocalFilesystemBlobStore(root=s.blob_store_local_root)
