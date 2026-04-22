"""Semantic memory - vector store abstraction + in-memory reference impl.

Namespaces partition the store so we can retrieve only from:
  - `chunks:{project_id}`
  - `requirements:{project_id}`
  - `knowledge:general`
  - `knowledge:{project_id}`
  - `lessons`                    (cross-project reviewer findings)

The in-memory reference uses numpy cosine. Swap in Qdrant / Chroma /
pgvector by implementing `SemanticStore` against those backends.
"""

from __future__ import annotations

from collections.abc import Sequence
from threading import RLock
from typing import Any

import numpy as np

from ai_testplan_generator.memory.base import SearchHit, SemanticStore


class InMemorySemanticStore(SemanticStore):
    def __init__(self) -> None:
        # namespace -> (ids[], matrix[N, D], payloads[])
        self._buckets: dict[str, _Bucket] = {}
        self._lock = RLock()

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
        arr = np.asarray(vectors, dtype=np.float32)
        # L2-normalise upfront so queries collapse to a simple matmul.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms

        with self._lock:
            bucket = self._buckets.get(namespace)
            if bucket is None:
                self._buckets[namespace] = _Bucket(
                    ids=list(ids), matrix=arr, payloads=list(payloads)
                )
                return
            # Upsert: overwrite matching ids, append the rest.
            id_to_idx = {eid: i for i, eid in enumerate(bucket.ids)}
            new_ids: list[str] = []
            new_rows: list[np.ndarray] = []
            new_payloads: list[dict[str, Any]] = []
            for i, eid in enumerate(ids):
                if eid in id_to_idx:
                    idx = id_to_idx[eid]
                    bucket.matrix[idx] = arr[i]
                    bucket.payloads[idx] = dict(payloads[i])
                else:
                    new_ids.append(eid)
                    new_rows.append(arr[i])
                    new_payloads.append(dict(payloads[i]))
            if new_ids:
                bucket.ids.extend(new_ids)
                bucket.matrix = np.vstack([bucket.matrix, np.stack(new_rows)])
                bucket.payloads.extend(new_payloads)

    async def query(
        self,
        vector: Sequence[float],
        *,
        namespace: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        with self._lock:
            bucket = self._buckets.get(namespace)
        if bucket is None or len(bucket.ids) == 0:
            return []

        q = np.asarray(vector, dtype=np.float32)
        q_norm = np.linalg.norm(q) or 1.0
        q = q / q_norm

        sims = bucket.matrix @ q  # (N,)
        # Apply filters BEFORE top-k to avoid returning filtered-out entries
        # with misleading high scores.
        if filters:
            mask = np.asarray(
                [_match(p, filters) for p in bucket.payloads], dtype=bool
            )
            if not mask.any():
                return []
            sims = np.where(mask, sims, -np.inf)

        k = min(top_k, int(np.isfinite(sims).sum()))
        if k <= 0:
            return []
        top_idx = np.argpartition(-sims, kth=k - 1)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]

        return [
            SearchHit(
                id=bucket.ids[int(i)],
                score=float(sims[int(i)]),
                payload=bucket.payloads[int(i)],
            )
            for i in top_idx
        ]

    async def delete_namespace(self, namespace: str) -> None:
        with self._lock:
            self._buckets.pop(namespace, None)


class _Bucket:
    __slots__ = ("ids", "matrix", "payloads")

    def __init__(
        self, ids: list[str], matrix: np.ndarray, payloads: list[dict[str, Any]]
    ) -> None:
        self.ids = ids
        self.matrix = matrix
        self.payloads = payloads


def _match(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    for k, v in filters.items():
        if isinstance(v, (list, tuple, set)):
            if payload.get(k) not in set(v):
                return False
        elif payload.get(k) != v:
            return False
    return True
