"""TraceabilityAgent - validates and enriches trace links.

Runs after generator. For each TestCase:
  - Verifies it genuinely covers the requirements it claims.
  - Looks for additional chunks the test depends on.
  - Computes the coverage matrix that goes on the TestPlan.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.models import Requirement, SourceEvidence, TestCase, TestPlan
from ai_testplan_generator.models.traceability import TraceKind, TraceLink
from ai_testplan_generator.prompts.library import TRACEABILITY_SYSTEM


class _TraceCheck(BaseModel):
    covers_confidence: float = Field(ge=0.0, le=1.0)
    additional_chunk_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    notes: str | None = None


class TraceabilityReport(BaseModel):
    plan_id: str
    coverage_matrix: dict[str, list[str]] = Field(default_factory=dict)
    weak_links: list[str] = Field(default_factory=list)  # test_case_ids
    contradictions: list[str] = Field(default_factory=list)


class _TraceInput(BaseModel):
    plan: TestPlan
    requirements: list[Requirement]


class TraceabilityAgent(BaseAgent[_TraceInput, TraceabilityReport]):
    name = "traceability"
    Input = _TraceInput

    async def run(self, inp: _TraceInput) -> TraceabilityReport:
        req_by_id = {r.id: r for r in inp.requirements}

        sem = asyncio.Semaphore(8)

        async def check(tc: TestCase) -> tuple[str, _TraceCheck | None]:
            async with sem:
                if not tc.requirement_ids:
                    return tc.id, None
                reqs = [req_by_id[rid] for rid in tc.requirement_ids if rid in req_by_id]
                if not reqs:
                    return tc.id, None
                source_chunks = []
                for r in reqs:
                    source_chunks.extend(
                        await self.ctx.memory.get_chunks_by_ids(r.source_chunk_ids)
                    )
                ctx_blob = "\n".join(f"[{c.id}] {c.text[:400]}" for c in source_chunks)
                messages = [
                    ChatMessage(role="system", content=TRACEABILITY_SYSTEM),
                    ChatMessage(
                        role="user",
                        content=(
                            f"TestCase:\n"
                            f" title: {tc.title}\n objective: {tc.objective}\n"
                            f" steps: {[s.action for s in tc.steps]}\n"
                            f" acceptance: {[c.statement for c in tc.acceptance_criteria]}\n\n"
                            f"Covered requirements:\n"
                            + "\n".join(f"- [{r.id}] {r.statement}" for r in reqs)
                            + f"\n\nSource chunks:\n{ctx_blob}"
                        ),
                    ),
                ]
                try:
                    out = await self.ctx.llm.complete_structured(
                        messages, _TraceCheck, role="balanced", temperature=0.0
                    )
                except Exception:
                    return tc.id, None
                return tc.id, out

        results = await asyncio.gather(*[check(tc) for tc in inp.plan.test_cases])

        weak_links: list[str] = []
        contradictions: list[str] = []
        tc_by_id = {tc.id: tc for tc in inp.plan.test_cases}
        for tc_id, rep in results:
            if rep is None:
                continue
            if rep.covers_confidence < 0.5:
                weak_links.append(tc_id)
            if rep.contradictions:
                contradictions.extend(f"{tc_id}: {c}" for c in rep.contradictions)
            for ch_id in rep.additional_chunk_ids:
                chunks = await self.ctx.memory.get_chunks_by_ids([ch_id])
                if chunks and tc_id in tc_by_id:
                    ch = chunks[0]
                    tc = tc_by_id[tc_id]
                    if not any(ev.chunk_id == ch.id for ev in tc.source_evidence):
                        tc.source_evidence.append(
                            SourceEvidence(
                                chunk_id=ch.id,
                                document_id=ch.document_id,
                                page_start=ch.page_start,
                                page_end=ch.page_end,
                                excerpt=ch.text[:500],
                                relation="traceability",
                            )
                        )
                self.ctx.memory.graph.add_link(
                    TraceLink(
                        kind=TraceKind.DERIVES_FROM,
                        source_id=tc_id,
                        source_type="TestCase",
                        target_id=ch_id,
                        target_type="Chunk",
                        confidence=rep.covers_confidence,
                        rationale=rep.notes,
                    )
                )

        coverage = self.ctx.memory.graph.coverage_matrix(req_by_id.keys())
        inp.plan.coverage_matrix = coverage
        return TraceabilityReport(
            plan_id=inp.plan.id,
            coverage_matrix=coverage,
            weak_links=weak_links,
            contradictions=contradictions,
        )
