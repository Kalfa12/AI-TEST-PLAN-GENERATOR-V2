"""TestGeneratorAgent - writes one TestCase per requirement (or small group).

Parallelised across requirements with a bounded semaphore. Each run
pulls the requirement's source chunks + related requirements for
context, then emits a structured TestCase that respects the chosen
detail level.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.memory.base import EpisodeEvent  # noqa: F401
from ai_testplan_generator.models import (
    AcceptanceCriterion,
    DetailLevel,
    Requirement,
    TestCase,
    TestStep,
)
from ai_testplan_generator.prompts.library import TEST_GENERATOR_SYSTEM


class _GenInput(BaseModel):
    requirements: list[Requirement]
    detail_level: DetailLevel = DetailLevel.DETAILED
    concurrency: int = 8


class _GenOutput(BaseModel):
    test_cases: list[TestCase]


class _DraftStep(BaseModel):
    action: str
    expected_result: str
    notes: str | None = None


class _DraftCriterion(BaseModel):
    statement: str
    measurable: bool = True
    tolerance: str | None = None


class _DraftCase(BaseModel):
    title: str
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    setup: str | None = None
    steps: list[_DraftStep] = Field(default_factory=list)
    acceptance_criteria: list[_DraftCriterion] = Field(default_factory=list)
    teardown: str | None = None
    estimated_duration_minutes: int | None = None
    risk_level: int = Field(ge=1, le=5, default=3)
    tags: list[str] = Field(default_factory=list)


class TestGeneratorAgent(BaseAgent[_GenInput, _GenOutput]):
    name = "generator"
    Input = _GenInput

    async def run(self, inp: _GenInput) -> _GenOutput:
        sem = asyncio.Semaphore(inp.concurrency)

        async def one(req: Requirement) -> TestCase | None:
            async with sem:
                return await self._generate_for_requirement(req, inp.detail_level)

        results = await asyncio.gather(*[one(r) for r in inp.requirements])
        cases = [r for r in results if r is not None]
        await self.ctx.memory.register_test_cases(cases)
        return _GenOutput(test_cases=cases)

    async def _generate_for_requirement(
        self, req: Requirement, detail_level: DetailLevel
    ) -> TestCase | None:
        # Retrieve the immediate source chunks + nearby context.
        source_chunks = await self.ctx.memory.get_chunks_by_ids(req.source_chunk_ids)
        bundle = await self.ctx.memory.retrieve(
            req.statement,
            project_id=self.ctx.project_id,
            top_k_chunks=5,
            top_k_requirements=3,
        )

        ctx_lines: list[str] = []
        for ch in source_chunks:
            ctx_lines.append(f"[SOURCE:{ch.id} p.{ch.page_start}] {ch.text}")
        for ch in bundle.chunks:
            if ch.id in req.source_chunk_ids:
                continue
            ctx_lines.append(f"[RELATED:{ch.id}] {ch.text[:500]}")

        messages = [
            ChatMessage(role="system", content=TEST_GENERATOR_SYSTEM),
            ChatMessage(
                role="user",
                content=(
                    f"Detail level: {detail_level.value}\n\n"
                    f"Requirement [{req.id}]:\n"
                    f" kind={req.kind.value}, priority={req.priority}\n"
                    f" title={req.title}\n"
                    f" statement={req.statement}\n"
                    f" rationale={req.rationale or '-'}\n"
                    f" acceptance_hint={req.acceptance_hint or '-'}\n"
                    f" excerpt={req.verbatim_excerpt or '-'}\n\n"
                    f"Context:\n" + "\n".join(ctx_lines)
                ),
            ),
        ]
        try:
            draft = await self.ctx.llm.complete_structured(
                messages, _DraftCase, role="balanced", temperature=0.2
            )
        except Exception as e:
            import structlog
            structlog.get_logger(__name__).error(
                "test_generation_failed", 
                req_id=req.id, 
                error=str(e),
                error_type=type(e).__name__
            )
            return None

        return TestCase(
            title=draft.title,
            objective=draft.objective,
            preconditions=draft.preconditions,
            equipment=draft.equipment,
            setup=draft.setup,
            steps=[
                TestStep(
                    index=i + 1,
                    action=s.action,
                    expected_result=s.expected_result,
                    notes=s.notes,
                )
                for i, s in enumerate(draft.steps)
            ],
            acceptance_criteria=[
                AcceptanceCriterion(
                    statement=c.statement, measurable=c.measurable, tolerance=c.tolerance
                )
                for c in draft.acceptance_criteria
            ],
            teardown=draft.teardown,
            requirement_ids=[req.id],
            estimated_duration_minutes=draft.estimated_duration_minutes,
            risk_level=draft.risk_level,
            tags=draft.tags,
        )
