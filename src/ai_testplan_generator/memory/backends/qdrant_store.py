"""Qdrant-backed semantic store (async).

Implements the `SemanticStore` protocol using the async Qdrant client.
Each namespace maps to a prefixed Qdrant collection. Payload indexes are
created on first upsert for fast server-side filtering.

Install: pip install qdrant-client  or  pip install ai-testplan-generator[vector-qdrant]

Configure:
    SEMANTIC_MEMORY_BACKEND=qdrant
    QDRANT_URL=http://localhost:6333
    QDRANT_API_KEY=                    # optional, Qdrant Cloud
    QDRANT_EMBEDDING_DIM=3072
    QDRANT_COLLECTION_PREFIX=aitpg
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import structlog

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _to_point_id(s: str) -> str:
    """Deterministically convert any string to a UUID5 for Qdrant point IDs."""
    return str(uuid.uuid5(_NS, s))

from ai_testplan_generator.memory.base import SearchHit

_log = structlog.get_logger(__name__)

try:
    from qdrant_client import AsyncQdrantClient, models as qmodels
except ImportError as exc:
    raise ImportError(
        "qdrant-client is required for the Qdrant backend. "
        "Install it with: pip install qdrant-client "
        "or: pip install ai-testplan-generator[vector-qdrant]"
    ) from exc

_BATCH_SIZE = 256

_PAYLOAD_INDEX_FIELDS = ["project_id", "scope", "document_id", "kind"]


def _collection_name(namespace: str, prefix: str) -> str:
    safe = namespace.replace(":", "_").replace("/", "_").replace("-", "_")
    return f"{prefix}_{safe}" if prefix else safe


class QdrantSemanticStore:
    """Persistent async vector store backed by Qdrant.

    One Qdrant collection per namespace. Collections are created on first
    upsert with cosine distance and the configured embedding dimension.
    Payload indexes are created once per collection for fast filtering.
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        embedding_dim: int,
        collection_prefix: str = "aitpg",
    ) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        self._embedding_dim = embedding_dim
        self._prefix = collection_prefix
        self._ensured: set[str] = set()

    async def _ensure_collection(self, namespace: str) -> str:
        name = _collection_name(namespace, self._prefix)
        if name in self._ensured:
            return name

        existing_resp = await self._client.get_collections()
        existing = {c.name for c in existing_resp.collections}

        if name not in existing:
            await self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=self._embedding_dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            _log.info("qdrant_collection_created", collection=name, dim=self._embedding_dim)

            for field in _PAYLOAD_INDEX_FIELDS:
                await self._client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )

        self._ensured.add(name)
        return name

    async def upsert(
        self,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
        *,
        namespace: str,
    ) -> None:
        if not ids:
            return
        collection = await self._ensure_collection(namespace)
        points = [
            qmodels.PointStruct(
                id=_to_point_id(eid),
                vector=list(vec),
                payload={"_id": eid, **payload},
            )
            for eid, vec, payload in zip(ids, vectors, payloads)
        ]
        for i in range(0, len(points), _BATCH_SIZE):
            batch = points[i : i + _BATCH_SIZE]
            await self._client.upsert(collection_name=collection, points=batch)
        _log.debug("qdrant_upsert", collection=collection, n=len(ids))

    async def query(
        self,
        vector: Sequence[float],
        *,
        namespace: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        collection = await self._ensure_collection(namespace)

        q_filter: qmodels.Filter | None = None
        if filters:
            conditions: list[qmodels.FieldCondition] = []
            for key, value in filters.items():
                if isinstance(value, (list, tuple, set)):
                    conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchAny(any=list(value)),
                        )
                    )
                else:
                    conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value),
                        )
                    )
            q_filter = qmodels.Filter(must=conditions)

        results = await self._client.query_points(
            collection_name=collection,
            query=list(vector),
            limit=top_k,
            query_filter=q_filter,
            with_payload=True,
        )

        hits = []
        for point in results.points:
            payload = dict(point.payload) if point.payload else {}
            original_id = payload.pop("_id", str(point.id))
            hits.append(SearchHit(id=original_id, score=point.score or 0.0, payload=payload))
        return hits

    async def delete_namespace(self, namespace: str) -> None:
        name = _collection_name(namespace, self._prefix)
        try:
            await self._client.delete_collection(collection_name=name)
            self._ensured.discard(name)
            _log.info("qdrant_collection_deleted", collection=name)
        except Exception:
            _log.warning("qdrant_delete_failed", collection=name)

    async def close(self) -> None:
        await self._client.close()
