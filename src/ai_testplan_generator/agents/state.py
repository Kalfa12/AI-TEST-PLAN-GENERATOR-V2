"""Shared state schemas for the LangGraph state machines.

Using Pydantic BaseModels (not TypedDicts) so we get runtime validation
and JSON-serialisable state for checkpointing.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.reviewer import ReviewReport
from ai_testplan_generator.agents.traceability import TraceabilityReport
from ai_testplan_generator.models import (
    DetailLevel,
    Document,
    Requirement,
    TestCase,
    TestPlan,
    TestSchedule,
)


class AgentMode(StrEnum):
    AUTONOMOUS = "autonomous"
    INTERACTIVE = "interactive"


class AutonomousState(BaseModel):
    """State shared between nodes in the autonomous graph."""

    session_id: str
    project_id: str | None = None
    goal: str  # human-readable objective ("Generate full test plan for product X")
    detail_level: DetailLevel = DetailLevel.DETAILED

    documents: list[Document] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    plan: TestPlan | None = None
    test_cases: list[TestCase] = Field(default_factory=list)

    # Review feedback loop.
    review_report: ReviewReport | None = None
    trace_report: TraceabilityReport | None = None
    revision_round: int = 0
    max_revision_rounds: int = 3

    # Planning.
    schedule: TestSchedule | None = None

    # Orchestration bookkeeping.
    last_route: str | None = None
    finished: bool = False
    error: str | None = None

    # Interactive mode: per-agent free-text feedback the user provided when
    # they rejected an earlier output. Each entry accumulates across rounds
    # so the agent can see the whole correction history.
    interactive: bool = False
    user_feedback: dict[str, list[str]] = Field(default_factory=dict)


class InteractiveState(BaseModel):
    """State for the chat/copilot graph."""

    session_id: str
    project_id: str | None = None
    user_message: str
    assistant_message: str = ""
    plan: TestPlan | None = None
    pending_action: str | None = None  # e.g. "add_test_case", "revise_criterion"
