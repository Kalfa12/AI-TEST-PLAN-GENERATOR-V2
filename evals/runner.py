"""Benchmark execution.

Each benchmark is run end-to-end and yields a `BenchmarkResult` that the
report layer can format.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from ai_testplan_generator.models import DefectInstance, Requirement
from ai_testplan_generator.quality import check_requirements

from evals.loader import Benchmark, load_prefab_requirements
from evals.scoring import (
    DefectScore,
    ExtractionScore,
    score_defects,
    score_extraction,
)


@dataclass
class BenchmarkResult:
    benchmark: Benchmark
    mode: str  # "static-only" | "full"
    requirements: list[Requirement] = field(default_factory=list)
    defects: list[DefectInstance] = field(default_factory=list)
    extraction: ExtractionScore | None = None
    defect_score: DefectScore | None = None
    elapsed_s: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Static-only path: prefab fixtures → static checks
# ---------------------------------------------------------------------------


def run_static_only(benchmark: Benchmark) -> BenchmarkResult:
    """Run defect detection against pre-extracted requirement fixtures.

    Doesn't exercise the LLM extractor. Scores only `expected_defects`.
    Use this for CI and for users without LLM keys.
    """
    started = time.perf_counter()
    result = BenchmarkResult(benchmark=benchmark, mode="static-only")

    if benchmark.prefab_requirements_path is None:
        result.error = (
            "no prefab_requirements.json — this benchmark needs --full or "
            "a fixtures file to run in --static-only mode"
        )
        result.elapsed_s = time.perf_counter() - started
        return result

    reqs = load_prefab_requirements(benchmark.prefab_requirements_path)
    result.requirements = reqs

    defects = check_requirements(reqs)
    result.defects = defects

    external_to_internal = {
        r.external_id: r.id for r in reqs if r.external_id is not None
    }
    result.defect_score = score_defects(
        defects, benchmark.expected_defects, external_to_internal=external_to_internal
    )
    # No extraction scoring in static-only mode — fixtures are by construction
    # a perfect extraction.
    result.elapsed_s = time.perf_counter() - started
    return result


# ---------------------------------------------------------------------------
# Full path: real ingestion pipeline + extractor
# ---------------------------------------------------------------------------


async def _run_full_async(benchmark: Benchmark) -> BenchmarkResult:
    started = time.perf_counter()
    result = BenchmarkResult(benchmark=benchmark, mode="full")

    # Lazy imports — the static-only path must work even when LLM deps
    # aren't installed.
    from ai_testplan_generator.config import get_settings
    from ai_testplan_generator.ingestion.chunking import HierarchicalChunker
    from ai_testplan_generator.ingestion.extraction import RequirementExtractor
    from ai_testplan_generator.ingestion.loaders import load_document
    from ai_testplan_generator.llm import get_gateway

    settings = get_settings()
    chunker = HierarchicalChunker(settings)

    document, blocks = load_document(
        benchmark.spec_path, project_id="eval", scope="project"
    )
    _, chunks = chunker.chunk(document, blocks)

    gateway = get_gateway()
    extractor = RequirementExtractor(gateway, project_id="eval")
    raw = await extractor.extract_from_chunks(chunks, concurrency=8)
    reqs = await extractor.deduplicate(raw)
    result.requirements = reqs

    # Score extraction.
    result.extraction = score_extraction(reqs, benchmark.expected_requirements)

    # Score defects.
    defects = check_requirements(reqs)
    result.defects = defects

    # Map external IDs (REQ-001) to the freshly-minted internal req.id.
    # Match by statement_excerpt — same logic the extraction scorer uses.
    external_to_internal: dict[str, str] = {}
    for exp in benchmark.expected_requirements:
        needle = " ".join(exp.statement_excerpt.lower().split())
        for r in reqs:
            haystack = " ".join(r.statement.lower().split())
            if needle in haystack:
                external_to_internal[exp.external_id] = r.id
                break

    result.defect_score = score_defects(
        defects,
        benchmark.expected_defects,
        external_to_internal=external_to_internal,
    )

    result.elapsed_s = time.perf_counter() - started
    return result


def run_full(benchmark: Benchmark) -> BenchmarkResult:
    """Synchronous wrapper around the async pipeline run."""
    try:
        return asyncio.run(_run_full_async(benchmark))
    except Exception as exc:
        return BenchmarkResult(
            benchmark=benchmark,
            mode="full",
            error=f"{type(exc).__name__}: {exc}",
        )


def run_one(benchmark: Benchmark, *, mode: str) -> BenchmarkResult:
    if mode == "static-only":
        return run_static_only(benchmark)
    if mode == "full":
        return run_full(benchmark)
    raise ValueError(f"Unknown mode '{mode}'")


def run_many(
    benchmarks: list[Benchmark], *, mode: str
) -> list[BenchmarkResult]:
    return [run_one(b, mode=mode) for b in benchmarks]
