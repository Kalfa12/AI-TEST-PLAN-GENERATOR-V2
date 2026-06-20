"""RequirementExtractorAgent - agent wrapper around the extraction pipeline.

Extraction primitives already live in `ingestion.extraction`; this agent
is the orchestration-side handle so the graph can route to it uniformly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.ingestion.extraction import RequirementExtractor
from ai_testplan_generator.models import Chunk, Requirement


class _ExtractInput(BaseModel):
    chunks: list[Chunk]
    concurrency: int = 16
    user_feedback: list[str] = Field(default_factory=list)


class _ExtractOutput(BaseModel):
    requirements: list[Requirement]


class RequirementExtractorAgent(BaseAgent[_ExtractInput, _ExtractOutput]):
    name = "extractor"
    Input = _ExtractInput

    async def run(self, inp: _ExtractInput) -> _ExtractOutput:
        industry = await self.ctx.project_industry()
        extractor = RequirementExtractor(
            self.ctx.llm,
            project_id=self.ctx.project_id,
            industry=industry,
            user_feedback=inp.user_feedback,
        )
        raw = await extractor.extract_from_chunks(inp.chunks, concurrency=inp.concurrency)
        deduped = await extractor.deduplicate(raw)
        await self.ctx.memory.register_requirements(deduped)
        return _ExtractOutput(requirements=deduped)
