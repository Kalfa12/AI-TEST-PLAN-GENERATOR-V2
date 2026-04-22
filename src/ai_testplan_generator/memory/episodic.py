"""Episodic memory: the ordered log of what happened.

Every user message, agent decision, tool call, reviewer finding, and
generated artefact is appended here. The supervisor uses it to reason
about loops ("we've already tried this"), the copilot uses it to build
conversation context, and the traceability agent uses it to audit why
a test case exists.

The in-memory impl is deliberately naive. Production deployments should
drop in SQLite/Postgres (sqlite-vec for search) or a log-store.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import datetime, timezone
from threading import RLock

from ai_testplan_generator.memory.base import EpisodeEvent, EpisodicStore


class InMemoryEpisodicStore(EpisodicStore):
    def __init__(self, *, max_events_per_session: int = 10_000) -> None:
        self._events: dict[str, deque[EpisodeEvent]] = defaultdict(
            lambda: deque(maxlen=max_events_per_session)
        )
        self._lock = RLock()

    async def append(self, event: EpisodeEvent) -> None:
        if event.ts is None:  # type: ignore[unreachable]
            event = event.model_copy(update={"ts": datetime.now(timezone.utc)})
        with self._lock:
            self._events[event.session_id].append(event)

    async def recent(
        self,
        session_id: str,
        *,
        limit: int = 50,
        kinds: Sequence[str] | None = None,
    ) -> list[EpisodeEvent]:
        with self._lock:
            events = list(self._events.get(session_id, []))
        if kinds:
            kinds_set = set(kinds)
            events = [e for e in events if e.kind in kinds_set]
        return events[-limit:]

    async def search(
        self, session_id: str, query: str, *, limit: int = 20
    ) -> list[EpisodeEvent]:
        # Trivial substring search. The semantic store is where real recall
        # happens; this is just for quick textual scans.
        q = query.lower()
        with self._lock:
            events = list(self._events.get(session_id, []))
        return [e for e in events if q in e.content.lower()][-limit:]
