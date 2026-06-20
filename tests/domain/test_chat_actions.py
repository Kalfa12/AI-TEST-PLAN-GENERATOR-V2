"""Validation and application of typed chat actions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.domain.chat_actions import (
    ChatAction,
    PendingChatAction,
    apply_pending_chat_action,
    validate_action_payload,
)
from ai_testplan_generator.models import DetailLevel, TestPlan as PlanModel


def test_add_test_case_payload_requires_typed_fields() -> None:
    with pytest.raises(ValidationError):
        validate_action_payload(
            ChatAction.ADD_TEST_CASE,
            {"plan_id": "plan_1", "title": "", "objective": "x"},
        )


async def test_apply_pending_add_test_case_updates_persisted_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = await ArtifactRepository.create(db_path=str(tmp_path / "app.db"))
    plan = PlanModel(
        id="plan_chat",
        project_id="proj_chat",
        title="Chat Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Qualification",
        strategy="Cover every requirement.",
    )
    await repo.save_test_plan(plan)

    pending = PendingChatAction(
        session_id="sess-chat",
        user_id="usr-chat",
        project_id="proj_chat",
        action=ChatAction.ADD_TEST_CASE,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        payload={
            "plan_id": plan.id,
            "title": "Chat-added test",
            "objective": "Verify a chat-requested behavior.",
            "requirement_ids": ["req_1"],
            "steps": [
                {
                    "action": "Run the behavior.",
                    "expected_result": "The behavior is observed.",
                }
            ],
            "acceptance_criteria": [
                {"statement": "Behavior is observed.", "measurable": True}
            ],
            "risk_level": 2,
            "tags": ["chat"],
        },
    )

    result = await apply_pending_chat_action(repo, pending)
    reloaded = await repo.get_test_plan(plan.id)

    assert result.changed is True
    assert reloaded is not None
    assert len(reloaded.test_cases) == 1
    assert reloaded.test_cases[0].title == "Chat-added test"
    assert reloaded.coverage_matrix == {"req_1": [reloaded.test_cases[0].id]}

    await repo.close()
