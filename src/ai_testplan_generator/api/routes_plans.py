"""Routes: autonomous plan generation & retrieval.

POST /projects/{project_id}/plans       — kick off a plan generation run
GET  /sessions/{session_id}             — poll status of an in-flight run
GET  /projects/{project_id}/plans/{id}  — fetch a completed plan
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_testplan_generator.api.deps import (
    get_brain,
    get_plan,
    get_plans_for_project,
    get_session,
    register_session,
    register_task,
    store_plan,
    update_session,
)
from ai_testplan_generator.models import DetailLevel, TestPlan
from ai_testplan_generator.pipelines.autonomous import AutonomousPipeline
from ai_testplan_generator.pipelines.brain import Brain

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["plans"])


# ---- request / response models ---------------------------------------------

class CreatePlanRequest(BaseModel):
    goal: str
    detail_level: DetailLevel = DetailLevel.DETAILED
    max_revision_rounds: int = Field(default=3, ge=1, le=10)


class CreatePlanResponse(BaseModel):
    session_id: str
    message: str = "Plan generation started."


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str  # "running" | "done" | "error"
    error: str | None = None
    plan_id: str | None = None
    n_requirements: int = 0
    n_test_cases: int = 0
    progress_events: list[dict[str, Any]] = Field(default_factory=list)


class PlanListItem(BaseModel):
    id: str
    title: str


# ---- background runner ------------------------------------------------------

async def _run_pipeline(
    brain: Brain,
    project_id: str,
    session_id: str,
    goal: str,
    detail_level: DetailLevel,
    max_revision_rounds: int,
) -> None:
    """Long-running coroutine executed as a background task."""
    try:
        pipeline = AutonomousPipeline(brain)
        result = await pipeline.run(
            project_id=project_id,
            goal=goal,
            detail_level=detail_level,
            max_revision_rounds=max_revision_rounds,
            session_id=session_id,
        )
        if result.plan:
            store_plan(result.plan, project_id=project_id)
        update_session(
            session_id,
            state=result.state,
            status="done",
        )
        _log.info("api_plan_done", session_id=session_id, plan_id=result.plan.id if result.plan else None)
    except Exception as exc:
        _log.error("api_plan_error", session_id=session_id, error=str(exc))
        update_session(session_id, status="error", error=str(exc))


# ---- endpoints --------------------------------------------------------------

@router.post("/projects/{project_id}/plans", response_model=CreatePlanResponse)
async def create_plan(
    project_id: str,
    body: CreatePlanRequest,
    brain: Brain = Depends(get_brain),
) -> CreatePlanResponse:
    """Start an autonomous plan-generation run (non-blocking).

    Returns a session_id that you can poll via GET /sessions/{session_id}.
    """
    from uuid import uuid4

    session_id = f"sess_{uuid4().hex[:10]}"

    # Seed the session registry with an initial state.
    from ai_testplan_generator.agents.state import AutonomousState

    initial = AutonomousState(
        session_id=session_id,
        project_id=project_id,
        goal=body.goal,
        detail_level=body.detail_level,
        max_revision_rounds=body.max_revision_rounds,
    )
    register_session(session_id, initial)

    # Kick off the long-running pipeline as a fire-and-forget task.
    task = asyncio.create_task(
        _run_pipeline(
            brain,
            project_id=project_id,
            session_id=session_id,
            goal=body.goal,
            detail_level=body.detail_level,
            max_revision_rounds=body.max_revision_rounds,
        )
    )
    register_task(session_id, task)

    return CreatePlanResponse(session_id=session_id)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def session_status(
    session_id: str,
    brain: Brain = Depends(get_brain),
) -> SessionStatusResponse:
    """Poll the status of an in-flight autonomous run."""
    entry = get_session(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    state = entry["state"]
    plan_id = state.plan.id if state.plan else None

    # Fetch recent episodic events for progress reporting.
    events = await brain.memory.episodic.recent(session_id, limit=20)
    progress = [
        {"ts": e.ts.isoformat(), "actor": e.actor, "kind": e.kind, "content": e.content}
        for e in events
    ]

    return SessionStatusResponse(
        session_id=session_id,
        status=entry["status"],
        error=entry.get("error"),
        plan_id=plan_id,
        n_requirements=len(state.requirements),
        n_test_cases=len(state.test_cases),
        progress_events=progress,
    )


@router.get("/projects/{project_id}/plans", response_model=list[PlanListItem])
async def list_plans(
    project_id: str,
    brain: Brain = Depends(get_brain),
) -> list[PlanListItem]:
    """List all completed plans for a project."""
    plans = get_plans_for_project(project_id)
    return [PlanListItem(id=p.id, title=p.title) for p in plans]


@router.get("/projects/{project_id}/plans/{plan_id}", response_model=TestPlan)
async def get_plan_detail(
    project_id: str,
    plan_id: str,
) -> TestPlan:
    """Retrieve a completed test plan by ID."""
    plan = get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found.")
    return plan
