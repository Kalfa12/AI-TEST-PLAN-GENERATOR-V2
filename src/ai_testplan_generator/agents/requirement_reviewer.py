"""RequirementReviewerAgent - LLM-tier critique of extracted requirements.

Runs after the extractor. Catches the LLM-detectable requirement defects
that static checks cannot reliably catch (ambiguity, implementation
bias, compound obligations, temporal ambiguity, etc.). Emits
`ReviewFinding`s keyed by `requirement_id`.
"""

from __future__ import annotations

from pydantic import BaseModel

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.agents.reviewer import ReviewReport
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.models import Requirement
from ai_testplan_generator.prompts.library import (
    REQUIREMENT_REVIEWER_SYSTEM,
    with_industry_context,
)


class _ReqReviewInput(BaseModel):
    requirements: list[Requirement]


class RequirementReviewerAgent(BaseAgent[_ReqReviewInput, ReviewReport]):
    name = "requirement_reviewer"
    Input = _ReqReviewInput

    async def run(self, inp: _ReqReviewInput) -> ReviewReport:
        if not inp.requirements:
            return ReviewReport(approved=True, findings=[])

        sample = inp.requirements[:80]
        blob = "\n".join(
            f"- [{r.id}] ({r.kind.value}, p{r.priority}) {r.statement}"
            + (f"  rationale: {r.rationale}" if r.rationale else "")
            for r in sample
        )
        industry = await self.ctx.project_industry()
        messages = [
            ChatMessage(
                role="system",
                content=with_industry_context(REQUIREMENT_REVIEWER_SYSTEM, industry),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Requirements to review ({len(sample)} of {len(inp.requirements)}):\n"
                    + blob
                ),
            ),
        ]
        report = await self.ctx.llm.complete_structured(
            messages, ReviewReport, role="smart", temperature=0.1
        )
        return report
