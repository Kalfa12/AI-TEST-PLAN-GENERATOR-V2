"""FastAPI application factory.

Creates and configures the ASGI app that wraps the AI Test Plan Generator brain.

Run with:
    uvicorn ai_testplan_generator.api.app:create_app --factory --reload

Or directly:
    python -m ai_testplan_generator.api.app
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_testplan_generator.api.deps import get_brain
from ai_testplan_generator.api.routes_chat import router as chat_router
from ai_testplan_generator.api.routes_ingest import router as ingest_router
from ai_testplan_generator.api.routes_plans import router as plans_router
from ai_testplan_generator.api.routes_trace import router as trace_router

_log = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Eagerly build the Brain on startup so the first request isn't slow."""
    _log.info("api_startup", message="Building Brain...")
    brain = get_brain()
    _log.info(
        "api_ready",
        llm_smart=brain.settings.models.smart,
        llm_balanced=brain.settings.models.balanced,
        llm_fast=brain.settings.models.fast,
    )
    yield
    _log.info("api_shutdown")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="AI Test Plan Generator",
        description=(
            "Provider-agnostic multi-agent REST API for industrial test plan generation. "
            "Ingest documents, generate traceable test plans, and chat with a QA copilot."
        ),
        version="0.1.0",
        lifespan=_lifespan,
    )

    # CORS — permissive for development; lock down in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- health probe -------------------------------------------------------

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    # ---- route groups -------------------------------------------------------

    app.include_router(ingest_router)
    app.include_router(plans_router)
    app.include_router(chat_router)
    app.include_router(trace_router)

    return app


# Allow `python -m ai_testplan_generator.api.app`
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
