"""TestPlan / TestCase / TestStep - the final generated artefacts.

Two output levels are required by the spec:
  - SUMMARY: the test-plan view (strategy, scope, traceability matrix).
  - DETAILED: the test-instructions view (every step, every criterion).
Both are the same object tree - just rendered differently. We carry the
detail level on the plan so downstream rendering knows what to emit.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class DetailLevel(StrEnum):
    SUMMARY = "summary"
    DETAILED = "detailed"


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"ac_{uuid4().hex[:10]}")
    statement: str
    measurable: bool = True  # False => qualitative / observational
    tolerance: str | None = None  # e.g. "<= 2% FS"


class TestStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"st_{uuid4().hex[:8]}")
    index: int
    action: str  # "Apply 12V DC to terminal T1"
    expected_result: str  # "Voltage at VOUT stabilises at 5.00 V +/- 50 mV"
    notes: str | None = None


class TestCase(BaseModel):
    """Single executable test derived from one or more requirements."""

    model_config = ConfigDict(frozen=False)

    id: str = Field(default_factory=lambda: f"tc_{uuid4().hex[:10]}")
    title: str
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    setup: str | None = None
    steps: list[TestStep] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    teardown: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int | None = None
    risk_level: int = Field(ge=1, le=5, default=3)
    tags: list[str] = Field(default_factory=list)
    # Reviewer feedback loop data.
    review_notes: list[str] = Field(default_factory=list)
    revision: int = 0


class TestPlan(BaseModel):
    """Top-level plan: scope, strategy, test cases, and traceability."""

    id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:8]}")
    project_id: str | None = None
    title: str
    detail_level: DetailLevel = DetailLevel.DETAILED
    scope: str
    out_of_scope: list[str] = Field(default_factory=list)
    strategy: str  # test strategy narrative
    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    # requirement_id -> [test_case_id, ...] matrix.
    coverage_matrix: dict[str, list[str]] = Field(default_factory=dict)
