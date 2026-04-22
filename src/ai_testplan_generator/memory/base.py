"""Abstract memory-store protocols.

Four distinct, independently-swappable tiers, mirroring human cognition:

  * Working memory     - ephemeral scratchpad for the current task.
  * Episodic memory    - what happened, in order: events, tool calls,
                         reviewer findings, user turns.
  * Semantic memory    - vector store of long-term facts (chunks,
                         requirements, lessons learnt).
  * Cross-document     - graph of relationships (chunk -> requirement ->
                         test case -> document), not a vector space.

Every agent talks to `MemoryManager`, which composes these four. Swap any
one for a production backend (Redis / Qdrant / Neo4j / ...) by writing
one adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    id: str
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)


class EpisodeEvent(BaseModel):
    ts: datetime
    session_id: str
    actor: str  # "user", "orchestrator", "reviewer", ...
    kind: str  # "message", "tool_call", "decision", "artifact", ...
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class WorkingMemoryStore(Protocol):
    """Per-session key/value scratchpad with TTL semantics."""

    def get(self, session_id: str, key: str) -> Any | None: ...
    def set(self, session_id: str, key: str, value: Any, *, ttl_s: int | None = None) -> None: ...
    def delete(self, session_id: str, key: str) -> None: ...
    def items(self, session_id: str) -> dict[str, Any]: ...
    def clear(self, session_id: str) -> None: ...


@runtime_checkable
class EpisodicStore(Protocol):
    async def append(self, event: EpisodeEvent) -> None: ...
    async def recent(
        self, session_id: str, *, limit: int = 50, kinds: Sequence[str] | None = None
    ) -> list[EpisodeEvent]: ...
    async def search(self, session_id: str, query: str, *, limit: int = 20) -> list[EpisodeEvent]:
        ...


@runtime_checkable
class SemanticStore(Protocol):
    """Vector store abstraction - all embeddings live here, not on chunks."""

    async def upsert(
        self,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
        *,
        namespace: str,
    ) -> None: ...

    async def query(
        self,
        vector: Sequence[float],
        *,
        namespace: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]: ...

    async def delete_namespace(self, namespace: str) -> None: ...
