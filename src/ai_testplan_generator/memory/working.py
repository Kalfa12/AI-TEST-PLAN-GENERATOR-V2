"""In-process working memory.

Used by agents for "just for now" state - the current draft plan, the
open review thread, the partial tool-call outputs. Dies with the process
by design; anything that should survive belongs in episodic or semantic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass
class _Entry:
    value: Any
    expires_at: float | None  # monotonic seconds; None => never expires


class WorkingMemory:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, _Entry]] = {}
        self._lock = RLock()

    def get(self, session_id: str, key: str) -> Any | None:
        with self._lock:
            bucket = self._store.get(session_id)
            if not bucket:
                return None
            entry = bucket.get(key)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at < time.monotonic():
                bucket.pop(key, None)
                return None
            return entry.value

    def set(self, session_id: str, key: str, value: Any, *, ttl_s: int | None = None) -> None:
        with self._lock:
            bucket = self._store.setdefault(session_id, {})
            bucket[key] = _Entry(
                value=value,
                expires_at=time.monotonic() + ttl_s if ttl_s is not None else None,
            )

    def delete(self, session_id: str, key: str) -> None:
        with self._lock:
            self._store.get(session_id, {}).pop(key, None)

    def items(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            bucket = self._store.get(session_id, {})
            now = time.monotonic()
            return {
                k: e.value
                for k, e in bucket.items()
                if e.expires_at is None or e.expires_at >= now
            }

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
