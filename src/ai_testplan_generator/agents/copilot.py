"""CopilotAgent - the interactive chat persona.

Grounded conversation: retrieves from memory, quotes sources, proposes
plan mutations but does not apply them without confirmation. Intended
to be driven one turn at a time from the interactive graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.llm.prompt_safety import (
    UNTRUSTED_DOCUMENT_POLICY,
    format_untrusted_document_chunk,
)
from ai_testplan_generator.memory.base import EpisodeEvent
from ai_testplan_generator.models import TestPlan
from ai_testplan_generator.prompts.library import COPILOT_SYSTEM, with_industry_context

CopilotAction = Literal[
    "none",
    "summarise_plan",
    "check_coverage",
    "add_test_case",
    "revise_test_case",
    "remove_test_case",
]


class CopilotReply(BaseModel):
    message: str
    citations: list[str] = Field(default_factory=list)  # "spec_v3.pdf p.41"
    proposed_action: CopilotAction = "none"
    action_payload: dict[str, Any] = Field(default_factory=dict)
    needs_confirmation: bool = False


class _CopilotInput(BaseModel):
    user_message: str
    max_history: int = 12


def _truncate(text: str, max_chars: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 1].rstrip()}..."


def _coverage_counts(plan: TestPlan) -> tuple[int, int, int]:
    total = len(plan.coverage_matrix)
    covered = sum(1 for case_ids in plan.coverage_matrix.values() if case_ids)
    if total == 0:
        linked_requirement_ids = {
            req_id for tc in plan.test_cases for req_id in tc.requirement_ids
        }
        total = len(linked_requirement_ids)
        covered = total
    percent = round((covered / total) * 100) if total else 0
    return covered, total, percent


def _format_generated_plan_context(plans: list[TestPlan]) -> str:
    latest = plans[0]
    lines = [
        "Generated project artefacts available to the assistant:",
        f"- Saved test plans: {len(plans)}",
    ]
    for plan in plans[:3]:
        covered, total, percent = _coverage_counts(plan)
        lines.append(
            "- Plan "
            f"{plan.id}: {plan.title}; detail={plan.detail_level.value}; "
            f"test_cases={len(plan.test_cases)}; "
            f"coverage={covered}/{total} ({percent}%)."
        )

    lines.append(f"\nLatest generated plan detail: {latest.id} - {latest.title}")
    if latest.scope:
        lines.append(f"Scope: {_truncate(latest.scope)}")
    if latest.strategy:
        lines.append(f"Strategy: {_truncate(latest.strategy)}")
    if latest.objectives:
        lines.append("Objectives: " + "; ".join(_truncate(o, 120) for o in latest.objectives[:5]))
    if latest.risks:
        lines.append("Risks: " + "; ".join(_truncate(r, 120) for r in latest.risks[:5]))

    lines.append("Latest plan test cases:")
    for tc in latest.test_cases[:12]:
        reqs = ", ".join(tc.requirement_ids) if tc.requirement_ids else "no linked requirements"
        lines.append(
            "- "
            f"{tc.id}: {tc.title}; status={tc.status.value}; risk={tc.risk_level}; "
            f"requirements=[{reqs}]; objective={_truncate(tc.objective, 180)}"
        )
    remaining = len(latest.test_cases) - 12
    if remaining > 0:
        lines.append(f"- ... {remaining} additional test cases omitted from prompt context.")
    return "\n".join(lines)


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

        if self.ctx.project_id:
            plans = await self.ctx.memory.get_test_plans_for_project(self.ctx.project_id)
            if plans:
                grounding.append(_format_generated_plan_context(plans))

        industry = await self.ctx.project_industry()
        messages: list[ChatMessage] = [
            ChatMessage(
                role="system",
                content=with_industry_context(COPILOT_SYSTEM, industry),
            )
        ]
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
