"""Health-check endpoints (M05).

GET /healthz  — liveness probe (always 200)
GET /readyz   — readiness probe (checks all configured backends)
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_project_repo,
    get_settings,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=True)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=True)
async def readiness(
    brain: Annotated[Brain, Depends(get_brain)],
    settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> JSONResponse:
    """Check that every configured backend is reachable."""
    checks: dict[str, str] = {"api": "ok"}
    unhealthy: list[str] = []

    checks["llm"] = "configured"

    await _check_semantic(brain, settings, checks, unhealthy)
    await _check_episodic(brain, settings, checks, unhealthy)
    _check_graph(brain, settings, checks, unhealthy)
    await _check_project_repo(project_repo, checks, unhealthy)
    await _check_blob_store(blob_store, checks, unhealthy)
    await _check_redis(settings, checks, unhealthy)

    status_code = 200 if not unhealthy else 503
    body: dict[str, Any] = {
        "status": "ok" if not unhealthy else "degraded",
        "checks": checks,
    }
    if unhealthy:
        body["unhealthy"] = unhealthy
    return JSONResponse(content=body, status_code=status_code)


async def _check_semantic(
    brain: Brain,
    settings: Settings,
    checks: dict[str, str],
    unhealthy: list[str],
) -> None:
    if settings.semantic_memory_backend == "inmemory":
        checks["semantic"] = "ok"
        return
    try:
        await brain.memory.semantic.query(
            vector=[0.0] * settings.qdrant_embedding_dim,
            namespace="_healthz",
            top_k=1,
        )
        checks["qdrant"] = "ok"
    except Exception as exc:
        _log.warning("readyz_qdrant_fail", error=str(exc))
        checks["qdrant"] = "unavailable"
        unhealthy.append("qdrant")


async def _check_episodic(
    brain: Brain,
    settings: Settings,
    checks: dict[str, str],
    unhealthy: list[str],
) -> None:
    if settings.episodic_memory_backend == "inmemory":
        checks["episodic"] = "ok"
        return
    try:
        await brain.memory.episodic.recent("_healthz", limit=1)
        checks["sqlite_episodic"] = "ok"
    except Exception as exc:
        _log.warning("readyz_episodic_fail", error=str(exc))
        checks["sqlite_episodic"] = "unavailable"
        unhealthy.append("sqlite_episodic")


def _check_graph(
    brain: Brain,
    settings: Settings,
    checks: dict[str, str],
    unhealthy: list[str],
) -> None:
    if settings.crossdoc_graph_backend == "networkx":
        checks["graph"] = "ok"
        return
    try:
        brain.memory.graph.to_dict()
        checks["neo4j"] = "ok"
    except Exception as exc:
        _log.warning("readyz_neo4j_fail", error=str(exc))
        checks["neo4j"] = "unavailable"
        unhealthy.append("neo4j")


async def _check_project_repo(
    repo: ProjectRepository,
    checks: dict[str, str],
    unhealthy: list[str],
) -> None:
    try:
        await repo.list_projects(limit=1)
        checks["project_db"] = "ok"
    except Exception as exc:
        _log.warning("readyz_project_repo_fail", error=str(exc))
        checks["project_db"] = "unavailable"
        unhealthy.append("project_db")


async def _check_blob_store(
    blob_store: BlobStore,
    checks: dict[str, str],
    unhealthy: list[str],
) -> None:
    key = f"_healthz/{uuid4().hex}.txt"
    try:
        await blob_store.put(key, b"ok", "text/plain")
        data = await blob_store.get(key)
        if data != b"ok":
            raise RuntimeError("blob store round-trip returned unexpected bytes")
        checks["blob_store"] = "ok"
    except Exception as exc:
        _log.warning("readyz_blob_store_fail", error=str(exc))
        checks["blob_store"] = "unavailable"
        unhealthy.append("blob_store")
    finally:
        try:
            await blob_store.delete(key)
        except Exception as exc:
            _log.warning("readyz_blob_store_cleanup_fail", error=str(exc))


async def _check_redis(
    settings: Settings,
    checks: dict[str, str],
    unhealthy: list[str],
) -> None:
    redis_required = (
        settings.event_broker_backend == "redis"
        or settings.semantic_memory_backend != "inmemory"
    )
    if not redis_required:
        checks["redis"] = "not_configured"
        return
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        client = aioredis.from_url(settings.redis_url)
        try:
            await client.ping()
        finally:
            await client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        _log.warning("readyz_redis_fail", error=str(exc))
        checks["redis"] = "unavailable"
        unhealthy.append("redis")
