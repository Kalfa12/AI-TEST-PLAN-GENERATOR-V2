"""TestArchitectAgent - drafts the plan-level strategy / scope / criteria.

Produces a TestPlan *shell*: scope, strategy, entry/exit criteria,
risks. The individual TestCases are filled in by the generator.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.models import DetailLevel, Requirement, TestPlan
from ai_testplan_generator.prompts.library import TEST_ARCHITECT_SYSTEM


class _ArchitectInput(BaseModel):
    goal: str
    detail_level: DetailLevel = DetailLevel.DETAILED
    requirements: list[Requirement] = Field(default_factory=list)


class _ArchitectOutput(BaseModel):
    title: str
    scope: str
    out_of_scope: list[str] = Field(default_factory=list)
    strategy: str
    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TestArchitectAgent(BaseAgent[_ArchitectInput, TestPlan]):
    name = "architect"
    Input = _ArchitectInput

    async def run(self, inp: _ArchitectInput) -> TestPlan:
        # Pull a synthesised view of the corpus from working memory if
        # the analyst ran earlier; otherwise retrieve on the fly.
        corpus = self.ctx.memory.working.get(self.ctx.session_id, "corpus_summary") or {}

        req_summary = [
            f"- [{r.kind.value}/{r.priority}] {r.title}: {r.statement}"
            for r in inp.requirements[:120]  # cap the prompt size
        ]
        overflow_note = (
            f"\n(+{len(inp.requirements) - 120} more requirements omitted from prompt - "
            "all will still be covered by the generator step.)"
            if len(inp.requirements) > 120
            else ""
        )

        messages = [
            ChatMessage(role="system", content=TEST_ARCHITECT_SYSTEM),
            ChatMessage(
                role="user",
                content=(
                    f"Goal: {inp.goal}\n"
                    f"Detail level: {inp.detail_level.value}\n"
                    f"Corpus summary: {corpus}\n\n"
                    f"Requirements ({len(inp.requirements)}):\n"
                    + "\n".join(req_summary)
                    + overflow_note
                ),
            ),
        ]
        shell = await self.ctx.llm.complete_structured(
            messages, _ArchitectOutput, role="smart", temperature=0.2
        )

        plan = TestPlan(
            project_id=self.ctx.project_id,
            title=shell.title,
            detail_level=inp.detail_level,
            scope=shell.scope,
            out_of_scope=shell.out_of_scope,
            strategy=shell.strategy,
            entry_criteria=shell.entry_criteria,
            exit_criteria=shell.exit_criteria,
            risks=shell.risks,
        )
        await self.ctx.memory.register_test_plan(plan)
        return plan
