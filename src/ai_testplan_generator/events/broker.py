"""Event broker protocol and in-memory implementation.

# TODO: swap InMemoryEventBroker for Redis Pub/Sub broker (M18).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventBroker(Protocol):
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


_SENTINEL: dict[str, Any] = {"__done__": True}
_TIMEOUT_S: float = 30.0


class InMemoryEventBroker:
    """Asyncio-queue-based broker for local/testing use.

    Topics follow the convention: ``session:{session_id}``, ``job:{job_id}``.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(topic, [])):
            await q.put(event)

    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subs[topic].append(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=_TIMEOUT_S)
                except asyncio.TimeoutError:
                    break
                if event.get("__done__"):
                    break
                yield event
        finally:
            topic_subs = self._subs.get(topic, [])
            if q in topic_subs:
                topic_subs.remove(q)

    async def close_topic(self, topic: str) -> None:
        """Signal all subscribers of a topic that the stream is done."""
        for q in list(self._subs.get(topic, [])):
            await q.put(_SENTINEL)
