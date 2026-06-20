"""Request/response schemas for chat/copilot endpoints (M08)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_testplan_generator.memory.base import EpisodeEvent


class ChatRequest(BaseModel):
    session_id: str | None = None
    project_id: str | None = None
    message: str


class ChatReply(BaseModel):
    session_id: str
    assistant_message: str
    pending_action: str | None = None
    unsupported_action: str | None = None


class ConfirmRequest(BaseModel):
    confirmed: bool = True


class HistoryResponse(BaseModel):
    session_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_events(cls, session_id: str, events: list[EpisodeEvent]) -> "HistoryResponse":
        return cls(
            session_id=session_id,
            events=[
                {
                    "ts": e.ts.isoformat(),
                    "actor": e.actor,
                    "kind": e.kind,
                    "content": e.content,
                    "metadata": e.metadata,
                }
                for e in events
            ],
        )
