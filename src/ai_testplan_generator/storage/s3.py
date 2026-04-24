"""S3-backed blob store (optional).

Install: pip install aioboto3  or  pip install ai-testplan-generator[storage-s3]

Configure:
    BLOB_STORE_BACKEND=s3
    S3_BUCKET=my-bucket
    S3_REGION=eu-west-1
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

_log = structlog.get_logger(__name__)

try:
    import aioboto3
except ImportError as exc:
    raise ImportError(
        "aioboto3 is required for the S3 blob backend. "
        "Install it with: pip install aioboto3 "
        "or: pip install ai-testplan-generator[storage-s3]"
    ) from exc

_CHUNK_SIZE = 64 * 1024  # 64 KB


class S3BlobStore:
    """Stores blobs as S3 objects. presign_get returns a pre-signed URL."""

    def __init__(self, *, bucket: str, region: str) -> None:
        self._bucket = bucket
        self._region = region
        self._session = aioboto3.Session()
        _log.info("s3_blob_store_init", bucket=bucket, region=region)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        async with self._session.client("s3", region_name=self._region) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        uri = f"s3://{self._bucket}/{key}"
        _log.debug("s3_blob_put", key=key, size=len(data))
        return uri

    async def get(self, key: str) -> bytes:
        async with self._session.client("s3", region_name=self._region) as s3:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            return await response["Body"].read()

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        async with self._session.client("s3", region_name=self._region) as s3:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            async for chunk in response["Body"].iter_chunks(_CHUNK_SIZE):
                yield chunk

    async def delete(self, key: str) -> None:
        async with self._session.client("s3", region_name=self._region) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
        _log.debug("s3_blob_delete", key=key)

    async def presign_get(self, key: str, expires_s: int = 900) -> str | None:
        async with self._session.client("s3", region_name=self._region) as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_s,
            )
        return url
