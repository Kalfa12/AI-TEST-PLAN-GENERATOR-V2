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

        llm = get_gateway()
        memory = MemoryManager(
            llm=llm,
            settings=cfg,
            episodic=episodic,
            semantic=semantic,
            graph=graph,
        )
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

        # In-memory event broker (swap for Redis in M18).
        from ai_testplan_generator.events.broker import InMemoryEventBroker

        event_broker = InMemoryEventBroker()

        # Attach everything to app.state.
        app.state.brain = brain
        app.state.blob_store = blob_store
        app.state.project_repo = project_repo
        app.state.event_broker = event_broker
        app.state.jobs: dict[str, Job] = {}
        app.state.plans: dict[str, Any] = {}
        app.state.project_plans: dict[str, list[str]] = {}

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

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
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
    # Routers
    # ------------------------------------------------------------------

    from ai_testplan_generator.api.routers.chat import router as chat_router
    from ai_testplan_generator.api.routers.documents import router as docs_router
    from ai_testplan_generator.api.routers.events import router as events_router
    from ai_testplan_generator.api.routers.health import router as health_router
    from ai_testplan_generator.api.routers.plans import router as plans_router
    from ai_testplan_generator.api.routers.projects import router as projects_router
    from ai_testplan_generator.api.routers.traceability import router as trace_router

    app.include_router(health_router)
    app.include_router(docs_router)
    app.include_router(plans_router)
    app.include_router(chat_router)
    app.include_router(trace_router)
    app.include_router(projects_router)
    app.include_router(events_router)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
