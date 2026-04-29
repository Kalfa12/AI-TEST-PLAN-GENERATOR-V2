"""Requirement extraction from chunks.

This is LLM-driven: we ask the fast-tier model to pull normative
statements out of each chunk and return them as structured Requirements.
The prompt is deliberately narrow - one chunk at a time - so we can
parallelise across a 10k-page doc without hitting any single context
window.

Map-reduce style:
  map:    chunk -> List[Requirement]
  reduce: deduplicate across the whole doc (cosine similarity on
          statement embeddings; downstream `TraceabilityAgent` keeps the
          stronger trace).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from ai_testplan_generator.llm import ChatMessage, LLMGateway
from ai_testplan_generator.models import Chunk, Requirement, RequirementKind
from ai_testplan_generator.prompts.library import REQUIREMENT_EXTRACTOR_SYSTEM


class _ExtractedRequirement(BaseModel):
    external_id: str | None = None
    kind: RequirementKind
    title: str
    statement: str
    rationale: str | None = None
    acceptance_hint: str | None = None
    priority: int = Field(ge=1, le=5, default=3)
    verbatim_excerpt: str | None = None


class _ExtractorOutput(BaseModel):
    requirements: list[_ExtractedRequirement] = Field(default_factory=list)


class RequirementExtractor:
    """LLM-powered extractor. One instance per project."""

    def __init__(
        self,
        gateway: LLMGateway,
        *,
        project_id: str | None = None,
        user_feedback: list[str] | None = None,
    ) -> None:
        self._llm = gateway
        self._project_id = project_id
        self._user_feedback = user_feedback or []

    async def extract_from_chunk(self, chunk: Chunk) -> list[Requirement]:
        # Skip chunks that are extremely unlikely to contain requirements.
        if chunk.kind.value not in {"prose", "table", "list"}:
            return []
        if len(chunk.text) < 30:
            return []

        feedback_block = ""
        if self._user_feedback:
            joined = "\n".join(f"- {f}" for f in self._user_feedback)
            feedback_block = (
                "\n\nUSER FEEDBACK FROM PREVIOUS ROUND(S) — apply these corrections:\n"
                f"{joined}\n"
            )

        messages = [
            ChatMessage(role="system", content=REQUIREMENT_EXTRACTOR_SYSTEM + feedback_block),
            ChatMessage(
                role="user",
                content=(
                    f"CHUNK_ID: {chunk.id}\n"
                    f"DOCUMENT_ID: {chunk.document_id}\n"
                    f"CHUNK_KIND: {chunk.kind.value}\n"
                    f"---\n{chunk.text}\n---"
                ),
            ),
        ]
        try:
            out = await self._llm.complete_structured(
                messages, _ExtractorOutput, role="fast", temperature=0.0
            )
        except Exception:
            # A single chunk failing must not tank the whole ingestion.
            return []

        return [
            Requirement(
                project_id=self._project_id,
                external_id=r.external_id,
                kind=r.kind,
                title=r.title,
                statement=r.statement,
                rationale=r.rationale,
                acceptance_hint=r.acceptance_hint,
                priority=r.priority,
                source_document_id=chunk.document_id,
                source_section_id=chunk.section_id,
                source_chunk_ids=[chunk.id],
                verbatim_excerpt=r.verbatim_excerpt,
            )
            for r in out.requirements
        ]

    async def extract_from_chunks(
        self,
        chunks: Iterable[Chunk],
        *,
        concurrency: int = 16,
    ) -> list[Requirement]:
        """Fan out across chunks under a bounded concurrency."""
        sem = asyncio.Semaphore(concurrency)

        async def one(c: Chunk) -> list[Requirement]:
            async with sem:
                return await self.extract_from_chunk(c)

        results = await asyncio.gather(*[one(c) for c in chunks])
        flat: list[Requirement] = []
        for batch in results:
            flat.extend(batch)
        return flat

    # -- reduce step: near-duplicate collapse ----------------------------------

    async def deduplicate(
        self, requirements: Sequence[Requirement], *, similarity_threshold: float = 0.92
    ) -> list[Requirement]:
        """Greedy cosine-dedup on statement embeddings."""
        if len(requirements) < 2:
            return list(requirements)

        import numpy as np  # noqa: PLC0415

        texts = [r.statement for r in requirements]
        vecs = np.asarray(await self._llm.embed(texts), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs /= norms

        kept_idx: list[int] = []
        kept_mat: list[np.ndarray] = []
        for i, v in enumerate(vecs):
            if kept_mat:
                sims = np.stack(kept_mat) @ v
                if float(sims.max()) >= similarity_threshold:
                    continue
            kept_idx.append(i)
            kept_mat.append(v)

        return [requirements[i] for i in kept_idx]
