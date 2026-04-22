"""General knowledge base.

Cross-project corpus: industry standards (ISO, IEC, ASME), internal
testing playbooks, reviewer lessons-learnt, vocabularies. Uploaded once,
used by every project.

Thin wrapper over the ingestion pipeline with `scope="general"` pinned.
"""

from __future__ import annotations

from pathlib import Path

from ai_testplan_generator.ingestion.pipeline import IngestionPipeline, IngestionResult


class GeneralKnowledgeBase:
    NAMESPACE_CHUNKS = "chunks:general"
    NAMESPACE_LESSONS = "lessons"

    def __init__(self, ingestion: IngestionPipeline) -> None:
        self._ingestion = ingestion

    async def ingest(self, path: Path | str, *, title: str | None = None) -> IngestionResult:
        return await self._ingestion.ingest_file(
            path,
            project_id=None,
            scope="general",
            title=title,
            extract_requirements=False,  # general KB is reference material, not project reqs
            embed_chunks=True,
        )

    async def ingest_many(self, paths: list[Path | str]) -> list[IngestionResult]:
        results: list[IngestionResult] = []
        for p in paths:
            results.append(await self.ingest(p))
        return results
