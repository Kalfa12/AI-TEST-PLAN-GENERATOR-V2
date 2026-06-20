"""DocumentAnalystAgent - produces a corpus-level summary and gap analysis.

Runs once per ingestion batch. Its output is cached in working memory
and reused by the architect / copilot to avoid re-reading whole docs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.llm.prompt_safety import (
    UNTRUSTED_DOCUMENT_POLICY,
    format_untrusted_document_chunk,
)
from ai_testplan_generator.models import Document
from ai_testplan_generator.prompts.library import with_industry_context


class CorpusSummary(BaseModel):
    title: str
    abstract: str
    key_subsystems: list[str] = Field(default_factory=list)
    standards_referenced: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)
    requirement_count_estimate: int = 0


class _AnalystInput(BaseModel):
    documents: list[Document]


class DocumentAnalystAgent(BaseAgent[_AnalystInput, CorpusSummary]):
    name = "analyst"
    Input = _AnalystInput  # re-exported for callers

    async def run(self, inp: _AnalystInput) -> CorpusSummary:
        # Hybrid retrieval over the whole project for a representative
        # snapshot - cheaper than feeding every doc.
        bundle = await self.ctx.memory.retrieve(
            "project scope, main subsystems, key standards, testability concerns",
            project_id=self.ctx.project_id,
            top_k_chunks=20,
            top_k_requirements=5,
        )
        context_lines: list[str] = []
        for ch in bundle.chunks:
            doc = next((d for d in inp.documents if d.id == ch.document_id), None)
            tag = doc.title if doc else ch.document_id
            context_lines.append(
                f"SOURCE_TITLE: {tag}\n"
                + format_untrusted_document_chunk(
                    chunk_id=ch.id,
                    document_id=ch.document_id,
                    kind=ch.kind.value,
                    page_start=ch.page_start,
                    page_end=ch.page_end,
                    text=ch.text,
                    max_chars=400,
                )
            )

        industry = await self.ctx.project_industry()
        system_prompt = with_industry_context(
            (
                "You summarise an industrial project's documentation corpus. "
                "Be concrete and terse. Your summary will be reused by "
                "downstream agents, so prefer specific subsystem names and "
                "standard references over generic labels."
            ),
            industry,
        )
        messages = [
            ChatMessage(
                role="system",
                content=system_prompt,
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Documents: {[d.title for d in inp.documents]}\n\n"
                    f"Representative excerpts:\n{UNTRUSTED_DOCUMENT_POLICY}\n\n"
                    + "\n\n".join(context_lines[:40])
                ),
            ),
        ]
        summary = await self.ctx.llm.complete_structured(
            messages, CorpusSummary, role="balanced", temperature=0.1
        )
        self.ctx.memory.working.set(self.ctx.session_id, "corpus_summary", summary.model_dump())
        return summary
