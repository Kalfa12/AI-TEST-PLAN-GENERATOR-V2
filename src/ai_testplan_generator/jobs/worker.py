"""ARQ WorkerSettings for the background job worker (M17).

Run with:
    arq ai_testplan_generator.jobs.worker.WorkerSettings
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from ai_testplan_generator.jobs.tasks.autonomous import (
    delete_project_artefacts,
    run_autonomous,
)
from ai_testplan_generator.jobs.tasks.ingest import ingest_document

_log = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """Build Brain, BlobStore, and EventBroker once per worker process."""
    from ai_testplan_generator.config import get_settings

    cfg = get_settings()

    from ai_testplan_generator.telemetry.logging import configure_logging
    from ai_testplan_generator.telemetry.otel import init_tracing

    configure_logging(cfg)
    init_tracing(cfg.otel_service_name, cfg.otel_exporter_otlp_endpoint)

    from ai_testplan_generator.events.broker import build_event_broker
    from ai_testplan_generator.ingestion.pipeline import IngestionPipeline
    from ai_testplan_generator.knowledge import GeneralKnowledgeBase
    from ai_testplan_generator.llm import get_gateway
    from ai_testplan_generator.domain.artifacts import ArtifactRepository
    from ai_testplan_generator.domain.jobs import JobRepository
    from ai_testplan_generator.domain.projects import ProjectRepository
    from ai_testplan_generator.memory.backends import (
        build_episodic_store,
        build_graph_store,
        build_semantic_store,
    )
    from ai_testplan_generator.memory.manager import MemoryManager
    from ai_testplan_generator.pipelines.brain import Brain
    from ai_testplan_generator.storage import build_blob_store

    episodic = await build_episodic_store(cfg)
    semantic = build_semantic_store(cfg)
    graph = build_graph_store(cfg)
    blob_store = build_blob_store(cfg)
    artifact_repo = await ArtifactRepository.create(db_path=cfg.app_db_path)
    job_repo = await JobRepository.create(db_path=cfg.app_db_path)
    project_repo = await ProjectRepository.create(db_path=cfg.app_db_path)

    llm = get_gateway()
    memory = MemoryManager(
        llm=llm,
        settings=cfg,
        episodic=episodic,
        semantic=semantic,
        graph=graph,
        artifact_repo=artifact_repo,
    )
    await memory.hydrate()
    ingestion = IngestionPipeline(llm=llm, memory=memory, settings=cfg)
    general_kb = GeneralKnowledgeBase(ingestion)
    brain = Brain(
        settings=cfg,
        llm=llm,
        memory=memory,
        ingestion=ingestion,
        general_kb=general_kb,
        project_repo=project_repo,
    )
    event_broker = build_event_broker(cfg)

    ctx["brain"] = brain
    ctx["blob_store"] = blob_store
    ctx["artifact_repo"] = artifact_repo
    ctx["job_repo"] = job_repo
    ctx["project_repo"] = project_repo
    ctx["event_broker"] = event_broker
    ctx["settings"] = cfg
    ctx["max_tries"] = WorkerSettings.max_tries
    # Per-worker in-process plan cache (populated by run_autonomous task).
    ctx["plans"] = {}
    ctx["project_plans"] = {}

    _log.info("arq_worker_ready")


async def shutdown(ctx: dict[str, Any]) -> None:
    brain = ctx.get("brain")
    if brain is not None:
        episodic = brain.memory.episodic
        if hasattr(episodic, "close"):
            await episodic.close()  # type: ignore[union-attr]
        graph = brain.memory.graph
        if hasattr(graph, "close"):
            await graph.close()  # type: ignore[union-attr]
        if brain.memory.artifact_repo is not None:
            await brain.memory.artifact_repo.close()

    job_repo = ctx.get("job_repo")
    if job_repo is not None:
        await job_repo.close()

    project_repo = ctx.get("project_repo")
    if project_repo is not None:
        await project_repo.close()

    event_broker = ctx.get("event_broker")
    if event_broker is not None and hasattr(event_broker, "close"):
        await event_broker.close()  # type: ignore[union-attr]

    _log.info("arq_worker_shutdown")


class WorkerSettings:
    """ARQ worker configuration.

    To run:
        arq ai_testplan_generator.jobs.worker.WorkerSettings
    """

    functions = [ingest_document, run_autonomous, delete_project_artefacts]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs: int = int(os.getenv("JOB_WORKER_CONCURRENCY", "4"))
    max_tries: int = 4  # 1 initial + 3 retries
    retry_jobs: bool = True
    job_timeout: int = 600  # 10 minutes per task
    keep_result: int = 3600  # keep results for 1 hour

    try:
        from arq.connections import RedisSettings as _RS  # type: ignore[import-untyped]

        redis_settings = _RS.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    except Exception:
        pass  # arq not installed — worker cannot run, but tests still import the module
