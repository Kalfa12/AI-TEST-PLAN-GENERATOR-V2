"""Scheduling / resourcing artefacts for section 7 of the spec."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Resource(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"res_{uuid4().hex[:8]}")
    project_id: str | None = None
    name: str
    service: str  # e.g. "Mechanical test lab"
    role: str | None = None  # "Technician", "Test Engineer", ...
    availability_pct: int = Field(ge=0, le=100, default=100)


class Milestone(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"ms_{uuid4().hex[:8]}")
    name: str
    due: date
    gate: bool = False  # gating milestone (cannot slip)
    depends_on: list[str] = Field(default_factory=list)


class TestSchedule(BaseModel):
    """Minimal schedule object - enough to feed a Gantt renderer later."""

    plan_id: str
    milestones: list[Milestone] = Field(default_factory=list)
    # test_case_id -> (start, end, resource_ids)
    assignments: dict[str, "ScheduledAssignment"] = Field(default_factory=dict)


class ScheduledAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: date
    end: date
    resource_ids: list[str] = Field(default_factory=list)
    service: str | None = None


TestSchedule.model_rebuild()
