"""End-to-end ingestion pipeline: file -> Document, Sections, Chunks, Requirements.

Holds everything together and commits to the memory tiers through the
`MemoryManager`. Safe for very large documents: the loader streams,
chunking runs per-section, extraction fans out under a bounded
semaphore, embeddings are batched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import structlog

from ai_testplan_generator.config import Settings, get_settings
from ai_testplan_generator.ingestion.chunking import HierarchicalChunker
from ai_testplan_generator.ingestion.extraction import RequirementExtractor
from ai_testplan_generator.ingestion.loaders import load_document
from ai_testplan_generator.llm import LLMGateway
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import Chunk, Document, Requirement, Section

_log = structlog.get_logger(__name__)


@dataclass
class IngestionResult:
    document: Document
    sections: list[Section] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)


class IngestionPipeline:
    def __init__(
        self,
        *,
        llm: LLMGateway,
        memory: MemoryManager,
        settings: Settings | None = None,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._settings = settings or get_settings()
        self._chunker = HierarchicalChunker(self._settings)

    async def ingest_file(
        self,
        path: Path | str,
        *,
        project_id: str | None = None,
        scope: Literal["general", "project"] = "project",
        title: str | None = None,
        extract_requirements: bool = True,
        embed_chunks: bool = True,
        extraction_concurrency: int = 16,
    ) -> IngestionResult:
        document, blocks = load_document(path, project_id=project_id, scope=scope, title=title)
        _log.info("ingest_start", document_id=document.id, uri=document.source_uri, scope=scope)

        sections, chunks = self._chunker.chunk(document, blocks)
        _log.info(
            "chunking_complete",
            document_id=document.id,
            n_sections=len(sections),
            n_chunks=len(chunks),
        )

        if len(chunks) > self._settings.max_doc_pages_warn:
            _log.warning(
                "very_large_document",
                document_id=document.id,
                n_chunks=len(chunks),
                hint="consider partitioning the source doc before ingest",
            )

        # Commit structural artefacts to memory first so anything we spawn
        # downstream can already retrieve them.
        await self._memory.register_document(document)
        await self._memory.register_sections(sections)
        await self._memory.register_chunks(chunks, embed=embed_chunks)

        requirements: list[Requirement] = []
        if extract_requirements:
            extractor = RequirementExtractor(self._llm, project_id=project_id)
            raw_reqs = await extractor.extract_from_chunks(
                chunks, concurrency=extraction_concurrency
            )
            requirements = await extractor.deduplicate(raw_reqs)
            await self._memory.register_requirements(requirements)
            _log.info(
                "requirement_extraction_complete",
                document_id=document.id,
                n_raw=len(raw_reqs),
                n_deduped=len(requirements),
            )

        return IngestionResult(
            document=document,
            sections=sections,
            chunks=chunks,
            requirements=requirements,
        )

    async def ingest_many(
        self,
        paths: list[Path | str],
        *,
        project_id: str | None = None,
        scope: Literal["general", "project"] = "project",
    ) -> list[IngestionResult]:
        results: list[IngestionResult] = []
        for p in paths:
            results.append(await self.ingest_file(p, project_id=project_id, scope=scope))
        return results
