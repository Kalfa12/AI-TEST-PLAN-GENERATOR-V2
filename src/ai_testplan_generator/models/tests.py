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


class SourceEvidence(BaseModel):
    """Compact source citation stored on generated test cases."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    page_start: int | None = None
    page_end: int | None = None
    excerpt: str
    relation: str = "source"


class TestCase(BaseModel):
    """Single executable test derived from one or more requirements.

    Fields align with the Inflectra test plan template columns:
    Test Item | Test Strategy | Testing Types | Features to be Tested |
    Features not to be Tested | Entry Criteria | Exit Criteria |
    Deliverables | Dependencies | KPIs | Risk Analysis | Assignee
    """

    model_config = ConfigDict(frozen=False)

    id: str = Field(default_factory=lambda: f"tc_{uuid4().hex[:10]}")
    title: str
    objective: str
    # Template: Testing Types column
    testing_types: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    # Template: Features not to be Tested column
    features_not_tested: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    setup: str | None = None
    steps: list[TestStep] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    teardown: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int | None = None
    risk_level: int = Field(ge=1, le=5, default=3)
    # Template: Risk Analysis column (narrative, complements risk_level)
    risk_description: str | None = None
    # Template: Deliverables column
    deliverables: list[str] = Field(default_factory=list)
    # Template: Dependencies column
    dependencies: list[str] = Field(default_factory=list)
    # Template: KPIs column
    kpis: list[str] = Field(default_factory=list)
    # Template: Assignee column
    assignee: str | None = None
    tags: list[str] = Field(default_factory=list)
    # Reviewer feedback loop data.
    review_notes: list[str] = Field(default_factory=list)
    revision: int = 0
    source_evidence: list[SourceEvidence] = Field(default_factory=list)


class TestPlan(BaseModel):
    """Top-level plan: scope, strategy, test cases, and traceability.

    Header fields align with the Inflectra test plan template:
    Test Plan ID | Name | Version | Author | Date | Introduction |
    Objectives | Scope | Out-of-Scope
    """

    id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:8]}")
    project_id: str | None = None
    title: str
    # Template: Document Version
    version: str = "v1.0"
    # Template: Test Plan Author
    author: str = "AI-Generated"
    detail_level: DetailLevel = DetailLevel.DETAILED
    # Template: Introduction
    introduction: str = ""
    # Template: Objectives (high-level goals, distinct from strategy narrative)
    objectives: list[str] = Field(default_factory=list)
    scope: str
    out_of_scope: list[str] = Field(default_factory=list)
    strategy: str  # test strategy narrative
    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    # requirement_id -> [test_case_id, ...] matrix.
    coverage_matrix: dict[str, list[str]] = Field(default_factory=dict)
