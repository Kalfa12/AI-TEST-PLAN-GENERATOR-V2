"""Typed, auditable chat actions for confirmed plan mutations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ai_testplan_generator.models import (
    AcceptanceCriterion,
    TestCase,
    TestPlan,
    TestStep,
)


class ChatAction(StrEnum):
    SUMMARISE_PLAN = "summarise_plan"
    CHECK_COVERAGE = "check_coverage"
    ADD_TEST_CASE = "add_test_case"
    REVISE_TEST_CASE = "revise_test_case"
    REMOVE_TEST_CASE = "remove_test_case"


MUTATING_ACTIONS = {
    ChatAction.ADD_TEST_CASE,
    ChatAction.REVISE_TEST_CASE,
    ChatAction.REMOVE_TEST_CASE,
}


class DraftStep(BaseModel):
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    notes: str | None = None


class DraftCriterion(BaseModel):
    statement: str = Field(min_length=1)
    measurable: bool = True
    tolerance: str | None = None


class PlanRefPayload(BaseModel):
    plan_id: str = Field(min_length=1)


class AddTestCasePayload(PlanRefPayload):
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    steps: list[DraftStep] = Field(default_factory=list)
    acceptance_criteria: list[DraftCriterion] = Field(default_factory=list)
    risk_level: int = Field(default=3, ge=1, le=5)
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)


class ReviseTestCasePayload(PlanRefPayload):
    test_case_id: str = Field(min_length=1)
    title: str | None = None
    objective: str | None = None
    requirement_ids: list[str] | None = None
    steps: list[DraftStep] | None = None
    acceptance_criteria: list[DraftCriterion] | None = None
    risk_level: int | None = Field(default=None, ge=1, le=5)
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None


class RemoveTestCasePayload(PlanRefPayload):
    test_case_id: str = Field(min_length=1)
    reason: str | None = None


PAYLOAD_SCHEMAS: dict[ChatAction, type[BaseModel]] = {
    ChatAction.SUMMARISE_PLAN: PlanRefPayload,
    ChatAction.CHECK_COVERAGE: PlanRefPayload,
    ChatAction.ADD_TEST_CASE: AddTestCasePayload,
    ChatAction.REVISE_TEST_CASE: ReviseTestCasePayload,
    ChatAction.REMOVE_TEST_CASE: RemoveTestCasePayload,
}


class PendingChatAction(BaseModel):
    id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:10]}")
    session_id: str
    user_id: str
    project_id: str
    action: ChatAction
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    consumed_at: datetime | None = None


class ChatMutationResult(BaseModel):
    action_id: str
    action: ChatAction
    project_id: str
    plan_id: str
    changed: bool
    message: str
    before_test_case_ids: list[str] = Field(default_factory=list)
    after_test_case_ids: list[str] = Field(default_factory=list)
    affected_test_case_ids: list[str] = Field(default_factory=list)


def validate_action_payload(action: str | ChatAction, payload: dict[str, Any]) -> BaseModel:
    action_enum = ChatAction(action)
    schema = PAYLOAD_SCHEMAS[action_enum]
    return schema.model_validate(payload)


def action_preview(action: str | ChatAction, payload: dict[str, Any]) -> str:
    action_enum = ChatAction(action)
    parsed = validate_action_payload(action_enum, payload)
    if action_enum == ChatAction.ADD_TEST_CASE:
        assert isinstance(parsed, AddTestCasePayload)
        return f"Add test case '{parsed.title}' to plan {parsed.plan_id}."
    if action_enum == ChatAction.REVISE_TEST_CASE:
        assert isinstance(parsed, ReviseTestCasePayload)
        fields = [
            name
            for name in (
                "title",
                "objective",
                "requirement_ids",
                "steps",
                "acceptance_criteria",
                "risk_level",
                "estimated_duration_minutes",
                "tags",
            )
            if getattr(parsed, name) is not None
        ]
        return (
            f"Revise test case {parsed.test_case_id} in plan {parsed.plan_id}"
            f" ({', '.join(fields) or 'no fields'})."
        )
    if action_enum == ChatAction.REMOVE_TEST_CASE:
        assert isinstance(parsed, RemoveTestCasePayload)
        return f"Remove test case {parsed.test_case_id} from plan {parsed.plan_id}."
    return f"{action_enum.value} for plan {parsed.plan_id}."


async def apply_pending_chat_action(repo: Any, pending: PendingChatAction) -> ChatMutationResult:
    parsed = validate_action_payload(pending.action, pending.payload)
    plan_id = parsed.plan_id  # type: ignore[attr-defined]
    plan = await repo.get_test_plan(plan_id)
    if plan is None or plan.project_id != pending.project_id:
        raise ValueError(f"Plan '{plan_id}' not found in project '{pending.project_id}'.")

    before_ids = [tc.id for tc in plan.test_cases]
    affected: list[str] = []
    if pending.action == ChatAction.ADD_TEST_CASE:
        assert isinstance(parsed, AddTestCasePayload)
        tc = _test_case_from_add(parsed)
        plan.test_cases.append(tc)
        affected.append(tc.id)
    elif pending.action == ChatAction.REVISE_TEST_CASE:
        assert isinstance(parsed, ReviseTestCasePayload)
        tc = _find_test_case(plan, parsed.test_case_id)
        _revise_test_case(tc, parsed)
        affected.append(tc.id)
    elif pending.action == ChatAction.REMOVE_TEST_CASE:
        assert isinstance(parsed, RemoveTestCasePayload)
        tc = _find_test_case(plan, parsed.test_case_id)
        plan.test_cases = [item for item in plan.test_cases if item.id != tc.id]
        affected.append(tc.id)
    else:
        raise ValueError(f"Action '{pending.action.value}' is not a mutating action.")

    _rebuild_coverage(plan)
    await repo.save_test_plan(plan)
    after_ids = [tc.id for tc in plan.test_cases]
    return ChatMutationResult(
        action_id=pending.id,
        action=pending.action,
        project_id=pending.project_id,
        plan_id=plan.id,
        changed=before_ids != after_ids or pending.action == ChatAction.REVISE_TEST_CASE,
        message=_result_message(pending.action, affected),
        before_test_case_ids=before_ids,
        after_test_case_ids=after_ids,
        affected_test_case_ids=affected,
    )


def _test_case_from_add(payload: AddTestCasePayload) -> TestCase:
    return TestCase(
        title=payload.title,
        objective=payload.objective,
        requirement_ids=payload.requirement_ids,
        steps=[
            TestStep(index=i + 1, action=step.action, expected_result=step.expected_result, notes=step.notes)
            for i, step in enumerate(payload.steps)
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                statement=criterion.statement,
                measurable=criterion.measurable,
                tolerance=criterion.tolerance,
            )
            for criterion in payload.acceptance_criteria
        ],
        risk_level=payload.risk_level,
        estimated_duration_minutes=payload.estimated_duration_minutes,
        tags=payload.tags,
    )


def _find_test_case(plan: TestPlan, test_case_id: str) -> TestCase:
    tc = next((item for item in plan.test_cases if item.id == test_case_id), None)
    if tc is None:
        raise ValueError(f"Test case '{test_case_id}' not found in plan '{plan.id}'.")
    return tc


def _revise_test_case(tc: TestCase, payload: ReviseTestCasePayload) -> None:
    if payload.title is not None:
        tc.title = payload.title
    if payload.objective is not None:
        tc.objective = payload.objective
    if payload.requirement_ids is not None:
        tc.requirement_ids = payload.requirement_ids
    if payload.steps is not None:
        tc.steps = [
            TestStep(
                index=i + 1,
                action=step.action,
                expected_result=step.expected_result,
                notes=step.notes,
            )
            for i, step in enumerate(payload.steps)
        ]
    if payload.acceptance_criteria is not None:
        tc.acceptance_criteria = [
            AcceptanceCriterion(
                statement=criterion.statement,
                measurable=criterion.measurable,
                tolerance=criterion.tolerance,
            )
            for criterion in payload.acceptance_criteria
        ]
    if payload.risk_level is not None:
        tc.risk_level = payload.risk_level
    if payload.estimated_duration_minutes is not None:
        tc.estimated_duration_minutes = payload.estimated_duration_minutes
    if payload.tags is not None:
        tc.tags = payload.tags


def _rebuild_coverage(plan: TestPlan) -> None:
    coverage: dict[str, list[str]] = {}
    for tc in plan.test_cases:
        for req_id in tc.requirement_ids:
            coverage.setdefault(req_id, []).append(tc.id)
    plan.coverage_matrix = coverage


def _result_message(action: ChatAction, affected: list[str]) -> str:
    target = ", ".join(affected) if affected else "no test case"
    if action == ChatAction.ADD_TEST_CASE:
        return f"Added {target}."
    if action == ChatAction.REVISE_TEST_CASE:
        return f"Revised {target}."
    if action == ChatAction.REMOVE_TEST_CASE:
        return f"Removed {target}."
    return "No mutation applied."
