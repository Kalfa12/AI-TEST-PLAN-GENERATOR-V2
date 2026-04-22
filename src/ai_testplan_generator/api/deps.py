"""Dependency injection for FastAPI routes.

Provides a process-wide `Brain` singleton and typed helpers that routes
can declare as dependencies via `Depends(get_brain)`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ai_testplan_generator.agents.state import AutonomousState
from ai_testplan_generator.pipelines.brain import Brain

# ---------------------------------------------------------------------------
# Brain singleton
# ---------------------------------------------------------------------------

_brain: Brain | None = None


def get_brain() -> Brain:
    """Return the process-wide Brain instance (created on first call)."""
    global _brain
    if _brain is None:
        _brain = Brain.build()
    return _brain


# ---------------------------------------------------------------------------
# In-process session store
# ---------------------------------------------------------------------------
# Autonomous runs are fire-and-forget background tasks. We keep a light
# registry of their state + asyncio.Task so the status endpoint can report
# progress without touching the graph runner itself.

_sessions: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task[Any]] = {}


def register_session(session_id: str, state: AutonomousState) -> None:
    _sessions[session_id] = {
        "state": state,
        "status": "running",
        "error": None,
    }


def update_session(session_id: str, *, state: AutonomousState | None = None,
                   status: str | None = None, error: str | None = None) -> None:
    entry = _sessions.get(session_id)
    if entry is None:
        return
    if state is not None:
        entry["state"] = state
    if status is not None:
        entry["status"] = status
    if error is not None:
        entry["error"] = error


def get_session(session_id: str) -> dict[str, Any] | None:
    return _sessions.get(session_id)


def register_task(session_id: str, task: asyncio.Task[Any]) -> None:
    _tasks[session_id] = task


def get_task(session_id: str) -> asyncio.Task[Any] | None:
    return _tasks.get(session_id)


# ---------------------------------------------------------------------------
# Plan store (in-process cache keyed by plan_id)
# ---------------------------------------------------------------------------

from ai_testplan_generator.models import TestPlan  # noqa: E402

_plans: dict[str, TestPlan] = {}
# Also track which plans belong to which project for listing/retrieval.
_project_plans: dict[str, list[str]] = {}


def store_plan(plan: TestPlan, project_id: str | None = None) -> None:
    _plans[plan.id] = plan
    pid = project_id or "__global__"
    _project_plans.setdefault(pid, []).append(plan.id)


def get_plan(plan_id: str) -> TestPlan | None:
    return _plans.get(plan_id)


def get_plans_for_project(project_id: str) -> list[TestPlan]:
    plan_ids = _project_plans.get(project_id, [])
    return [_plans[pid] for pid in plan_ids if pid in _plans]
