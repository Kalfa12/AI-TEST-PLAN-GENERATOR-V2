"""Request/response schemas for plan generation endpoints (M07)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_testplan_generator.models import DetailLevel, TestPlan


class CreatePlanRequest(BaseModel):
    goal: str
    detail_level: DetailLevel = DetailLevel.DETAILED
    max_revision_rounds: int = Field(default=1, ge=1, le=10)


class CreatePlanAccepted(BaseModel):
    job_id: str
    session_id: str
    message: str = "Plan generation started."


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


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


class TestCaseSummary(BaseModel):
    id: str
    title: str
    objective: str
    requirement_ids: list[str] = Field(default_factory=list)
    risk_level: int
    estimated_duration_minutes: int | None = None
    tags: list[str] = Field(default_factory=list)


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
                    estimated_duration_minutes=tc.estimated_duration_minutes,
                    tags=tc.tags,
                )
                for tc in plan.test_cases
            ],
        )
