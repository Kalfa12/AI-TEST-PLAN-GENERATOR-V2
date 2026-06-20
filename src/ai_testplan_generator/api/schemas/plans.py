"""Request/response schemas for plan generation endpoints (M07)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_testplan_generator.models import DetailLevel, TestCaseStatus, TestPlan


class CreatePlanRequest(BaseModel):
    goal: str
    detail_level: DetailLevel = DetailLevel.DETAILED
    max_revision_rounds: int = Field(default=1, ge=1, le=10)
    # When true, the run pauses after extractor / architect / generator
    # for user accept-or-reprompt feedback before continuing.
    interactive: bool = False


class CreatePlanAccepted(BaseModel):
    job_id: str
    session_id: str
    message: str = "Plan generation started."


class JobStatusResponse(BaseModel):
    # Shape mirrors the `Job` dataclass so existing tests and the frontend's
    # `JobStatus` interface remain backwards-compatible.
    id: str
    kind: str = ""
    status: str
    session_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    paused_at: str | None = None


class CheckpointResponse(BaseModel):
    job_id: str
    paused_at: str  # "extractor" | "architect" | "generator"
    state: dict[str, Any]  # serialised AutonomousState


class ResumeRequest(BaseModel):
    action: str  # "accept" | "reprompt" | "abort"
    feedback: str | None = None


class PlanListItem(BaseModel):
    id: str
    title: str
    detail_level: str
    n_test_cases: int


class PlanListResponse(BaseModel):
    items: list[PlanListItem] = Field(default_factory=list)
    total: int = 0


class CoverageMatrixResponse(BaseModel):
    plan_id: str
    matrix: dict[str, list[str]] = Field(default_factory=dict)


class GenerateRequirementTestCaseRequest(BaseModel):
    feedback: str | None = Field(
        default=None,
        description="Optional instruction to steer the single-requirement repair.",
    )


class TestCaseSummary(BaseModel):
    id: str
    title: str
    objective: str
    requirement_ids: list[str] = Field(default_factory=list)
    risk_level: int
    risk_description: str | None = None
    estimated_duration_minutes: int | None = None
    assignee: str | None = None
    status: TestCaseStatus = TestCaseStatus.NOT_STARTED
    status_note: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_evidence: list[dict[str, object]] = Field(default_factory=list)


class GenerateRequirementTestCaseResponse(BaseModel):
    plan_id: str
    requirement_id: str
    test_case: TestCaseSummary
    coverage_matrix: dict[str, list[str]] = Field(default_factory=dict)


class TestPlanSummary(BaseModel):
    id: str
    project_id: str | None
    title: str
    detail_level: str
    scope: str
    strategy: str
    n_test_cases: int
    test_cases: list[TestCaseSummary] = Field(default_factory=list)

    @classmethod
    def from_plan(cls, plan: TestPlan) -> "TestPlanSummary":
        return cls(
            id=plan.id,
            project_id=plan.project_id,
            title=plan.title,
            detail_level=plan.detail_level.value,
            scope=plan.scope,
            strategy=plan.strategy,
            n_test_cases=len(plan.test_cases),
            test_cases=[
                TestCaseSummary(
                    id=tc.id,
                    title=tc.title,
                    objective=tc.objective,
                    requirement_ids=tc.requirement_ids,
                    risk_level=tc.risk_level,
                    risk_description=tc.risk_description,
                    estimated_duration_minutes=tc.estimated_duration_minutes,
                    assignee=tc.assignee,
                    status=tc.status,
                    status_note=tc.status_note,
                    tags=tc.tags,
                    source_evidence=[
                        ev.model_dump(mode="json") for ev in tc.source_evidence
                    ],
                )
                for tc in plan.test_cases
            ],
        )
