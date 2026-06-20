"""ReviewerAgent - critique loop.

Runs after generator + traceability. Emits structured findings with
severity so the orchestrator can decide whether to loop back to
generator (critical/major issues) or move on (only minor issues).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.models import TestPlan
from ai_testplan_generator.models.defects import DefectType
from ai_testplan_generator.prompts.library import REVIEWER_SYSTEM, with_industry_context

Severity = Literal["critical", "major", "minor"]


class ReviewFinding(BaseModel):
    test_case_id: str | None = None
    requirement_id: str | None = None
    severity: Severity
    summary: str
    suggestion: str
    defect_type: DefectType | None = None


class ReviewReport(BaseModel):
    approved: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    overall_notes: str | None = None


class _ReviewInput(BaseModel):
    plan: TestPlan


class ReviewerAgent(BaseAgent[_ReviewInput, ReviewReport]):
    name = "reviewer"
    Input = _ReviewInput

    async def run(self, inp: _ReviewInput) -> ReviewReport:
        # Keep the reviewer prompt bounded; if the plan is huge we sample.
        sample = inp.plan.test_cases[:80]
        blob_tcs = []
        for tc in sample:
            blob_tcs.append(
                f"- [{tc.id}] {tc.title}\n"
                f"  covers: {tc.requirement_ids}\n"
                f"  steps: {[s.action for s in tc.steps[:4]]}\n"
                f"  criteria: {[c.statement for c in tc.acceptance_criteria[:4]]}"
            )

        industry = await self.ctx.project_industry()
        messages = [
            ChatMessage(
                role="system",
                content=with_industry_context(REVIEWER_SYSTEM, industry),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"TestPlan [{inp.plan.id}] - {inp.plan.title}\n"
                    f"Scope: {inp.plan.scope}\n"
                    f"Strategy: {inp.plan.strategy}\n"
                    f"Exit criteria: {inp.plan.exit_criteria}\n"
                    f"Coverage matrix size: {len(inp.plan.coverage_matrix)} requirements\n\n"
                    f"Test cases ({len(inp.plan.test_cases)} total, showing first {len(sample)}):\n"
                    + "\n".join(blob_tcs)
                ),
            ),
        ]
        report = await self.ctx.llm.complete_structured(
            messages, ReviewReport, role="smart", temperature=0.1
        )
        # Persist findings per-test-case for the generator to pick up.
        by_id = {tc.id: tc for tc in inp.plan.test_cases}
        for f in report.findings:
            if f.test_case_id and f.test_case_id in by_id:
                by_id[f.test_case_id].review_notes.append(f"[{f.severity}] {f.suggestion}")
        return report
