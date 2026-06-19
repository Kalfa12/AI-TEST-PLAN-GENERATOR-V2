"""FastAPI application factory (M05).

Entry point:
    uvicorn ai_testplan_generator.api.app:create_app --factory --port 8000
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog
import structlog.contextvars
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_testplan_generator.api.errors import AppError
from ai_testplan_generator.api.jobs import Job
from ai_testplan_generator.config import Settings, get_settings as _get_settings

if TYPE_CHECKING:
    pass

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

def _make_lifespan(settings: Settings | None) -> Any:  # returns contextmanager
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or _get_settings()
        app.state.settings = cfg

        # Initialise OTel tracing (no-op when OTEL_ENABLED=false).
        from ai_testplan_generator.telemetry.otel import init_tracing

        init_tracing(cfg.otel_service_name, cfg.otel_exporter_otlp_endpoint)

        _log.info("api_startup", semantic=cfg.semantic_memory_backend,
                  episodic=cfg.episodic_memory_backend, graph=cfg.crossdoc_graph_backend)

        # Build memory backends (episodic needs async init).
        from ai_testplan_generator.memory.backends import (
            build_episodic_store,
            build_graph_store,
            build_semantic_store,
        )

        episodic = await build_episodic_store(cfg)
        semantic = build_semantic_store(cfg)
        graph = build_graph_store(cfg)

        # Build blob store.
        from ai_testplan_generator.storage import build_blob_store

        blob_store = build_blob_store(cfg)

        # Build LLM gateway + compose Brain.
        from ai_testplan_generator.ingestion.pipeline import IngestionPipeline
        from ai_testplan_generator.knowledge import GeneralKnowledgeBase
        from ai_testplan_generator.llm import get_gateway
        from ai_testplan_generator.memory.manager import MemoryManager
        from ai_testplan_generator.pipelines.brain import Brain
        from ai_testplan_generator.domain.artifacts import ArtifactRepository

        artifact_repo = await ArtifactRepository.create(db_path=cfg.app_db_path)

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
        )

        # Build project repository (async SQLite init).
        from ai_testplan_generator.domain.projects import ProjectRepository

        project_repo = await ProjectRepository.create(db_path=cfg.app_db_path)

        # Build user repository (same SQLite file, separate connection).
        from ai_testplan_generator.domain.users import UserRepository

        user_repo = await UserRepository.create(db_path=cfg.app_db_path)

        # Event broker — InMemoryEventBroker or RedisPubSubBroker depending on settings (M18).
        from ai_testplan_generator.events.broker import build_event_broker

        event_broker = build_event_broker(cfg)
        # Give the brain a reference so agents can publish per-step SSE events.
        brain.event_broker = event_broker

        app.state.jobs: dict[str, Job] = {}
        app.state.plans: dict[str, Any] = {}
        app.state.project_plans: dict[str, list[str]] = {}
        app.state.defects: dict[str, Any] = {}

        # ARQ Redis pool and job queue (M17).
        job_queue = None
        redis_pool = None
        if cfg.semantic_memory_backend == "inmemory":
            from ai_testplan_generator.jobs.queue import FakeJobQueue
            job_queue = FakeJobQueue(
                brain=brain,
                blob_store=blob_store,
                event_broker=event_broker,
                plans=app.state.plans,
                project_plans=app.state.project_plans,
                defects=app.state.defects,
            )
            _log.info("arq_pool_bypassed", reason="inmemory_semantic_backend")
        else:
            try:
                import arq  # type: ignore[import-untyped]

                from arq.connections import RedisSettings
                redis_pool = await arq.create_pool(
                    RedisSettings.from_dsn(cfg.redis_url)  # type: ignore[attr-defined]
                )
                from ai_testplan_generator.jobs.queue import JobQueue

                job_queue = JobQueue(redis_pool)
                _log.info("arq_pool_connected", redis_url=cfg.redis_url)
            except Exception as arq_err:
                _log.warning("arq_pool_unavailable", error=str(arq_err))

        # Attach everything to app.state.
        app.state.brain = brain
        app.state.blob_store = blob_store
        app.state.project_repo = project_repo
        app.state.user_repo = user_repo
        app.state.artifact_repo = artifact_repo
        app.state.event_broker = event_broker
        app.state.job_queue = job_queue  # None when Redis is unavailable
        app.state.redis_pool = redis_pool

        _log.info("api_ready",
                  llm_smart=cfg.models.smart,
                  llm_balanced=cfg.models.balanced,
                  llm_fast=cfg.models.fast)
        yield

        # Graceful shutdown.
        if hasattr(episodic, "close"):
            await episodic.close()  # type: ignore[union-attr]
        if hasattr(graph, "close"):
            await graph.close()  # type: ignore[union-attr]
        await project_repo.close()
        await user_repo.close()
        await artifact_repo.close()
        if redis_pool is not None:
            await redis_pool.aclose()
        if hasattr(event_broker, "close"):
            await event_broker.close()  # type: ignore[union-attr]
        _log.info("api_shutdown")

    return _lifespan


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(*, settings: Settings | None = None) -> FastAPI:
    """Build and return the configured FastAPI application.

    Parameters
    ----------
    settings:
        Inject a pre-built Settings object (useful in tests). When None,
        the factory reads from environment / .env via ``get_settings()``.
    """
    cfg = settings or _get_settings()

    # Configure structlog before any log calls.
    from ai_testplan_generator.telemetry.logging import configure_logging

    configure_logging(cfg)

    # Initialise Prometheus registry when metrics are enabled.
    if cfg.metrics_enabled:
        from ai_testplan_generator.telemetry.metrics import init_metrics

        init_metrics()

    app = FastAPI(
        title="AI Test Plan Generator",
        description=(
            "Provider-agnostic multi-agent REST API for industrial test plan generation. "
            "Ingest documents, generate traceable test plans, and chat with a QA copilot."
        ),
        version="0.1.0",
        lifespan=_make_lifespan(settings),
    )

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from ai_testplan_generator.api.middleware.audit import AuditMiddleware

    app.add_middleware(AuditMiddleware, db_path=cfg.app_db_path)

    if cfg.metrics_enabled:
        from ai_testplan_generator.api.middleware.prometheus_mw import PrometheusMiddleware

        app.add_middleware(PrometheusMiddleware)

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Inject OTel trace/span IDs so log lines carry trace correlation.
        from ai_testplan_generator.telemetry.otel import current_trace_context

        trace_ctx = current_trace_context()
        if trace_ctx:
            structlog.contextvars.bind_contextvars(**trace_ctx)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # Bind user_id if authentication resolved a user during request handling.
        user = getattr(request.state, "current_user", None)
        if user is not None:
            structlog.contextvars.bind_contextvars(user_id=user.id)

        structlog.contextvars.unbind_contextvars("request_id")
        return response

    # ------------------------------------------------------------------
    # Global exception handler
    # ------------------------------------------------------------------

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID", "")
        _log.warning("app_error", error_code=exc.error_code, detail=exc.detail,
                     status=exc.status_code, request_id=request_id)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": request_id,
                     "error_code": exc.error_code},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID", "")
        _log.error("unhandled_error", error=str(exc), request_id=request_id)
        detail = str(exc) if cfg.api_debug else "An unexpected error occurred."
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "request_id": request_id,
                     "error_code": "INTERNAL_ERROR"},
        )

    # ------------------------------------------------------------------
    # Metrics endpoint — must NOT require authentication
    # ------------------------------------------------------------------

    @app.get("/metrics", include_in_schema=False)
    async def _metrics_endpoint() -> Any:
        if not cfg.metrics_enabled:
            from fastapi import Response

            return Response(status_code=404)
        from prometheus_client import generate_latest  # type: ignore[import-untyped]

        from ai_testplan_generator.telemetry.metrics import get_registry
        from fastapi.responses import Response as _Response

        return _Response(
            content=generate_latest(get_registry()),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------

    from ai_testplan_generator.api.routers.admin import router as admin_router
    from ai_testplan_generator.api.routers.auth import router as auth_router
    from ai_testplan_generator.api.routers.chat import router as chat_router
    from ai_testplan_generator.api.routers.documents import router as docs_router
    from ai_testplan_generator.api.routers.events import router as events_router
    from ai_testplan_generator.api.routers.health import router as health_router
    from ai_testplan_generator.api.routers.plans import router as plans_router
    from ai_testplan_generator.api.routers.projects import router as projects_router
    from ai_testplan_generator.api.routers.quality import router as quality_router
    from ai_testplan_generator.api.routers.traceability import router as trace_router

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(docs_router)
    app.include_router(plans_router)
    app.include_router(quality_router)
    app.include_router(chat_router)
    app.include_router(trace_router)
    app.include_router(projects_router)
    app.include_router(events_router)
    app.include_router(admin_router)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
