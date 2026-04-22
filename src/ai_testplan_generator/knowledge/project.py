"""Project-specific knowledge base.

One instance per project. Holds the project's spec sheets, requirement
docs, customer norms, interface control documents - everything that
drives the test plan for THIS specific engagement.

All requirement extraction happens here; the general KB is deliberately
not extracted from (it would pollute the test matrix with third-party
normative statements).
"""

from __future__ import annotations

from pathlib import Path

from ai_testplan_generator.ingestion.pipeline import IngestionPipeline, IngestionResult


class ProjectKnowledgeBase:
    def __init__(self, ingestion: IngestionPipeline, project_id: str) -> None:
        self._ingestion = ingestion
        self.project_id = project_id

    async def ingest(
        self, path: Path | str, *, title: str | None = None, extract_requirements: bool = True
    ) -> IngestionResult:
        return await self._ingestion.ingest_file(
            path,
            project_id=self.project_id,
            scope="project",
            title=title,
            extract_requirements=extract_requirements,
            embed_chunks=True,
        )

    async def ingest_many(self, paths: list[Path | str]) -> list[IngestionResult]:
        results: list[IngestionResult] = []
        for p in paths:
            results.append(await self.ingest(p))
        return results
