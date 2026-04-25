"""Health-check endpoints (M05).

GET /healthz  — liveness probe (always 200)
GET /readyz   — readiness probe (checks all configured backends)
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ai_testplan_generator.api.deps import get_brain, get_project_repo, get_settings
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.pipelines.brain import Brain

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
) -> JSONResponse:
    """Check that every configured backend is reachable."""
    checks: dict[str, str] = {}
    unhealthy: list[str] = []

    checks["llm"] = "configured"

    await _check_semantic(brain, settings, checks, unhealthy)
    await _check_episodic(brain, settings, checks, unhealthy)
    _check_graph(brain, settings, checks, unhealthy)
    await _check_project_repo(project_repo, checks, unhealthy)

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
