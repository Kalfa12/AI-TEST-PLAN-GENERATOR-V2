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
    pending_action_id: str | None = None
    pending_action_preview: str | None = None
    unsupported_action: str | None = None


class ChatPlanContext(BaseModel):
    id: str
    title: str
    n_test_cases: int
    covered_requirements: int = 0
    total_requirements: int = 0
    coverage_percent: int = 0


class ChatContextResponse(BaseModel):
    project_id: str
    project_name: str
    industry: str
    documents: int = 0
    requirements: int = 0
    plans: int = 0
    latest_plan: ChatPlanContext | None = None


class ConfirmRequest(BaseModel):
    confirmed: bool = True
    action_id: str | None = None


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
