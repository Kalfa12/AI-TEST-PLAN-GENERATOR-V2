"""Qdrant-backed semantic store.

Implements the `SemanticStore` protocol using the Qdrant vector database.
Namespaces map to Qdrant collections. Filters translate to Qdrant's
native filter API for efficient server-side filtering.

Install: `pip install qdrant-client` or `pip install ai-testplan-generator[vector-qdrant]`

Configure:
    SEMANTIC_MEMORY_BACKEND=qdrant
    QDRANT_URL=http://localhost:6333     # or your Qdrant Cloud URL
    QDRANT_API_KEY=                      # optional, for Qdrant Cloud
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog

from ai_testplan_generator.memory.base import SearchHit

_log = structlog.get_logger(__name__)

try:
    from qdrant_client import QdrantClient, models as qmodels
except ImportError as exc:
    raise ImportError(
        "qdrant-client is required for the Qdrant backend. "
        "Install it with: pip install qdrant-client  "
        "or: pip install ai-testplan-generator[vector-qdrant]"
    ) from exc


def _collection_name(namespace: str) -> str:
    """Convert a namespace string to a valid Qdrant collection name."""
    return namespace.replace(":", "_").replace("/", "_")


class QdrantSemanticStore:
    """Persistent vector store backed by Qdrant.

    Each namespace becomes a separate Qdrant collection. Vectors are stored
    un-normalised — Qdrant handles cosine distance natively.
    """

    def __init__(
        self,
        *,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        embedding_dim: int = 3072,  # text-embedding-3-large default
    ) -> None:
        self._client = QdrantClient(url=url, api_key=api_key)
        self._embedding_dim = embedding_dim
        self._ensured: set[str] = set()

    def _ensure_collection(self, namespace: str) -> str:
        """Create collection if it doesn't exist yet. Returns collection name."""
        name = _collection_name(namespace)
        if name in self._ensured:
            return name
        existing = {c.name for c in self._client.get_collections().collections}
        if name not in existing:
            self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=self._embedding_dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            _log.info("qdrant_collection_created", collection=name, dim=self._embedding_dim)
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
        collection = self._ensure_collection(namespace)
        points = [
            qmodels.PointStruct(
                id=eid,
                vector=list(vec),
                payload=dict(payload),
            )
            for eid, vec, payload in zip(ids, vectors, payloads)
        ]
        # Qdrant supports batch upsert; chunk if > 100 for safety.
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(collection_name=collection, points=batch)
        _log.debug("qdrant_upsert", collection=collection, n=len(ids))

    async def query(
        self,
        vector: Sequence[float],
        *,
        namespace: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        collection = self._ensure_collection(namespace)

        # Build Qdrant filter from our simple key=value dict.
        q_filter = None
        if filters:
            conditions = []
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

        results = self._client.query_points(
            collection_name=collection,
            query=list(vector),
            limit=top_k,
            query_filter=q_filter,
            with_payload=True,
        )

        return [
            SearchHit(
                id=str(point.id),
                score=point.score or 0.0,
                payload=dict(point.payload) if point.payload else {},
            )
            for point in results.points
        ]

    async def delete_namespace(self, namespace: str) -> None:
        name = _collection_name(namespace)
        try:
            self._client.delete_collection(collection_name=name)
            self._ensured.discard(name)
            _log.info("qdrant_collection_deleted", collection=name)
        except Exception:
            _log.warning("qdrant_delete_failed", collection=name)
