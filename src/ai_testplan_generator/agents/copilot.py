"""CopilotAgent - the interactive chat persona.

Grounded conversation: retrieves from memory, quotes sources, proposes
plan mutations but does not apply them without confirmation. Intended
to be driven one turn at a time from the interactive graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.llm.prompt_safety import (
    UNTRUSTED_DOCUMENT_POLICY,
    format_untrusted_document_chunk,
)
from ai_testplan_generator.memory.base import EpisodeEvent
from ai_testplan_generator.prompts.library import COPILOT_SYSTEM

CopilotAction = Literal[
    "none",
    "add_test_case",
    "revise_test_case",
    "remove_test_case",
    "change_detail_level",
]


class CopilotReply(BaseModel):
    message: str
    citations: list[str] = Field(default_factory=list)  # "spec_v3.pdf p.41"
    proposed_action: CopilotAction = "none"
    action_payload: dict[str, str] = Field(default_factory=dict)
    needs_confirmation: bool = False


class _CopilotInput(BaseModel):
    user_message: str
    max_history: int = 12


class CopilotAgent(BaseAgent[_CopilotInput, CopilotReply]):
    name = "copilot"
    Input = _CopilotInput

    async def run(self, inp: _CopilotInput) -> CopilotReply:
        recent = await self.ctx.memory.episodic.recent(
            self.ctx.session_id, limit=inp.max_history, kinds=["message"]
        )
        history = [
            ChatMessage(role="user" if e.actor == "user" else "assistant", content=e.content)
            for e in recent
        ]

        bundle = await self.ctx.memory.retrieve(
            inp.user_message,
            project_id=self.ctx.project_id,
            top_k_chunks=6,
            top_k_requirements=4,
        )
        grounding: list[str] = []
        for ch in bundle.chunks:
            grounding.append(
                format_untrusted_document_chunk(
                    chunk_id=ch.id,
                    document_id=ch.document_id,
                    kind=ch.kind.value,
                    page_start=ch.page_start,
                    page_end=ch.page_end,
                    text=ch.text,
                    max_chars=500,
                )
            )
        for r in bundle.requirements:
            grounding.append(f"[req:{r.id}] {r.title} - {r.statement}")

        messages: list[ChatMessage] = [ChatMessage(role="system", content=COPILOT_SYSTEM)]
        if grounding:
            messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        "Retrieved context:\n"
                        f"{UNTRUSTED_DOCUMENT_POLICY}\n\n"
                        + "\n\n".join(grounding)
                    ),
                )
            )
        messages.extend(history)
        messages.append(ChatMessage(role="user", content=inp.user_message))

        reply = await self.ctx.llm.complete_structured(
            messages, CopilotReply, role="balanced", temperature=0.3
        )

        now = datetime.now(timezone.utc)
        await self.ctx.memory.episodic.append(
            EpisodeEvent(
                ts=now,
                session_id=self.ctx.session_id,
                actor="user",
                kind="message",
                content=inp.user_message,
            )
        )
        await self.ctx.memory.episodic.append(
            EpisodeEvent(
                ts=now,
                session_id=self.ctx.session_id,
                actor="copilot",
                kind="message",
                content=reply.message,
            )
        )
        return reply
