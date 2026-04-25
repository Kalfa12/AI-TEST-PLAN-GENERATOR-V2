"""Event broker protocol and implementations (M11 / M18).

InMemoryEventBroker  — asyncio.Queue-based, used in tests and local dev.
RedisPubSubBroker    — Redis Pub/Sub, used in production (M18).
build_event_broker() — factory that picks the right impl from settings.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ai_testplan_generator.config import Settings


@runtime_checkable
class EventBroker(Protocol):
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...
    async def close_topic(self, topic: str) -> None: ...
    async def close(self) -> None: ...


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

    async def close(self) -> None:
        """No-op — nothing to release for the in-memory broker."""


# ---------------------------------------------------------------------------
# M18 — Redis Pub/Sub broker
# ---------------------------------------------------------------------------

class RedisPubSubBroker:
    """Redis Pub/Sub backed event broker for production use (M18).

    Requires ``redis[asyncio]`` to be installed.
    """

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        self._redis: Any = aioredis.from_url(redis_url, decode_responses=True)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        await self._redis.publish(topic, json.dumps(event))

    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        pubsub: Any = self._redis.pubsub()
        await pubsub.subscribe(topic)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                event = json.loads(data)
                if event.get("__done__"):
                    break
                yield event
        finally:
            try:
                await pubsub.unsubscribe(topic)
                await pubsub.aclose()
            except Exception:
                pass

    async def close_topic(self, topic: str) -> None:
        """Publish a sentinel so subscribers exit their listen loop."""
        await self._redis.publish(topic, json.dumps(_SENTINEL))

    async def close(self) -> None:
        await self._redis.aclose()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_event_broker(settings: "Settings") -> InMemoryEventBroker | RedisPubSubBroker:
    """Return the event broker configured by ``settings.event_broker_backend``."""
    if settings.event_broker_backend == "redis":
        return RedisPubSubBroker(settings.redis_url)
    return InMemoryEventBroker()
