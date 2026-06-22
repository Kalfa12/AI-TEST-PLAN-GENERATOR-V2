"""Phase 9: audited chat mutations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from ai_testplan_generator.agents.copilot import CopilotReply
from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api.deps import (
    get_brain,
    get_current_user,
    get_project_repo,
    get_settings,
    get_user_repo,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.domain.chat_actions import ChatAction, PendingChatAction
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User, UserRepository
from ai_testplan_generator.llm.base import ChatMessage, LLMResponse, ModelRole
from ai_testplan_generator.models import DetailLevel, TestPlan as PlanModel
from ai_testplan_generator.pipelines.brain import Brain
from tests.conftest import make_document, make_requirement, make_test_case


class MutatingCopilotLLM:
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        stop: Sequence[str] | None = None,
    ) -> LLMResponse:
        return LLMResponse(text="OK", model="mock-model", input_tokens=1, output_tokens=1)

    async def complete_structured(
        self,
        messages: Sequence[ChatMessage],
        schema: type[BaseModel],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> BaseModel:
        if schema is CopilotReply:
            return schema(
                message="I can add a focused test case after confirmation.",
                proposed_action="add_test_case",
                needs_confirmation=True,
                action_payload={
                    "plan_id": "plan_chat",
                    "title": "Chat-added safety test",
                    "objective": "Verify the chat-requested safety behavior.",
                    "requirement_ids": ["req_safety"],
                    "steps": [
                        {
                            "action": "Trigger the safety condition.",
                            "expected_result": "The controller enters a safe state.",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "statement": "The controller reaches the safe state.",
                            "measurable": True,
                        }
                    ],
                    "risk_level": 4,
                    "tags": ["chat", "safety"],
                },
            )
        raise AssertionError(f"Unexpected structured schema: {schema.__name__}")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield "OK"

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        input_type: str = "passage",
    ) -> list[list[float]]:
        return [[0.1] * 8 for _ in texts]


@dataclass
class ChatMutationRuntime:
    client: AsyncClient
    artifact_repo: ArtifactRepository
    project_repo: ProjectRepository
    user_repo: UserRepository
    db_path: str

    async def close(self) -> None:
        await self.client.aclose()
        await self.artifact_repo.close()
        await self.project_repo.close()
        await self.user_repo.close()


async def _build_runtime(tmp_path: Path, user: User) -> ChatMutationRuntime:
    db_path = str(tmp_path / "app.db")
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        APP_DB_PATH=db_path,
        API_DEBUG=True,
    )
    artifact_repo = await ArtifactRepository.create(db_path=db_path)
    brain = Brain.build(
        llm=MutatingCopilotLLM(),
        settings=settings,
        artifact_repo=artifact_repo,
    )
    project_repo = await ProjectRepository.create(db_path=db_path)
    brain.project_repo = project_repo
    user_repo = await UserRepository.create(db_path=db_path)

    app = create_app(settings=settings)
    app.dependency_overrides[get_brain] = lambda: brain
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_user_repo] = lambda: user_repo
    app.dependency_overrides[get_current_user] = lambda: user

    client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )
    return ChatMutationRuntime(
        client=client,
        artifact_repo=artifact_repo,
        project_repo=project_repo,
        user_repo=user_repo,
        db_path=db_path,
    )


async def _audit_metadata(db_path: str, action_like: str) -> dict[str, Any]:
    await asyncio.sleep(0.05)
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            """
            SELECT metadata FROM audit_events
            WHERE action LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"%{action_like}%",),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    return json.loads(row[0])


@pytest.mark.asyncio
async def test_chat_context_summarises_project_artifacts(tmp_path: Path) -> None:
    user = User(
        id="usr_chat",
        email="chat@test.local",
        display_name="Chat User",
        is_admin=True,
    )
    runtime = await _build_runtime(tmp_path, user)
    try:
        project = await runtime.project_repo.create_project(
            "Chat Context Project",
            owner_id=user.id,
        )
        document = make_document(project_id=project.id, title="System Spec")
        requirement = make_requirement(
            project_id=project.id,
            source_document_id=document.id,
            statement="The system shall retry transient failures.",
        )
        test_case = make_test_case(
            title="Retry transient failure",
            requirement_ids=[requirement.id],
        )
        plan = PlanModel(
            id="plan_context",
            project_id=project.id,
            title="Context Plan",
            detail_level=DetailLevel.DETAILED,
            scope="Retry handling",
            strategy="Cover the transient failure path.",
            test_cases=[test_case],
            coverage_matrix={requirement.id: [test_case.id]},
        )
        await runtime.artifact_repo.save_document(document)
        await runtime.artifact_repo.save_requirements([requirement])
        await runtime.artifact_repo.save_test_plan(plan)

        response = await runtime.client.get(
            "/chat/context",
            params={"project_id": project.id},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["project_id"] == project.id
        assert body["project_name"] == "Chat Context Project"
        assert body["documents"] == 1
        assert body["requirements"] == 1
        assert body["plans"] == 1
        assert body["latest_plan"] == {
            "id": "plan_context",
            "title": "Context Plan",
            "n_test_cases": 1,
            "covered_requirements": 1,
            "total_requirements": 1,
            "coverage_percent": 100,
        }
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_chat_proposes_then_confirm_applies_and_audits(tmp_path: Path) -> None:
    user = User(
        id="usr_chat",
        email="chat@test.local",
        display_name="Chat User",
        is_admin=True,
    )
    runtime = await _build_runtime(tmp_path, user)
    try:
        await runtime.project_repo.create_project("Chat Project", owner_id=user.id)
        plan = PlanModel(
            id="plan_chat",
            project_id="proj_chat",
            title="Chat Plan",
            detail_level=DetailLevel.DETAILED,
            scope="Qualification",
            strategy="Cover every requirement.",
        )
        await runtime.artifact_repo.save_test_plan(plan)

        response = await runtime.client.post(
            "/chat",
            json={
                "session_id": "sess-chat",
                "project_id": "proj_chat",
                "message": "Add a safety test to plan_chat.",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["pending_action"] == "add_test_case"
        assert body["pending_action_id"].startswith("act_")
        assert "Chat-added safety test" in body["pending_action_preview"]

        before = await runtime.artifact_repo.get_test_plan("plan_chat")
        assert before is not None
        assert before.test_cases == []

        confirm = await runtime.client.post(
            "/chat/sess-chat/confirm",
            json={"confirmed": True, "action_id": body["pending_action_id"]},
        )
        assert confirm.status_code == 200
        assert "Added" in confirm.json()["assistant_message"]

        after = await runtime.artifact_repo.get_test_plan("plan_chat")
        assert after is not None
        assert len(after.test_cases) == 1
        assert after.test_cases[0].title == "Chat-added safety test"
        assert after.coverage_matrix == {"req_safety": [after.test_cases[0].id]}

        metadata = await _audit_metadata(runtime.db_path, "CHAT_CONFIRM:add_test_case")
        assert metadata["before_test_case_ids"] == []
        assert metadata["after_test_case_ids"] == [after.test_cases[0].id]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_chat_discard_consumes_pending_action_without_mutating(tmp_path: Path) -> None:
    user = User(
        id="usr_chat",
        email="chat@test.local",
        display_name="Chat User",
        is_admin=True,
    )
    runtime = await _build_runtime(tmp_path, user)
    try:
        plan = PlanModel(
            id="plan_chat",
            project_id="proj_chat",
            title="Chat Plan",
            detail_level=DetailLevel.DETAILED,
            scope="Qualification",
            strategy="Cover every requirement.",
        )
        await runtime.artifact_repo.save_test_plan(plan)

        response = await runtime.client.post(
            "/chat",
            json={
                "session_id": "sess-chat",
                "project_id": "proj_chat",
                "message": "Add a safety test to plan_chat.",
            },
        )
        assert response.status_code == 200
        action_id = response.json()["pending_action_id"]

        discard = await runtime.client.post(
            "/chat/sess-chat/confirm",
            json={"confirmed": False, "action_id": action_id},
        )
        assert discard.status_code == 200
        assert "Discarded" in discard.json()["assistant_message"]

        reloaded = await runtime.artifact_repo.get_test_plan("plan_chat")
        assert reloaded is not None
        assert reloaded.test_cases == []

        no_pending = await runtime.client.post(
            "/chat/sess-chat/confirm",
            json={"confirmed": True, "action_id": action_id},
        )
        assert no_pending.status_code == 422
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_confirm_rejects_user_without_project_access(tmp_path: Path) -> None:
    user = User(
        id="usr_intruder",
        email="intruder@test.local",
        display_name="Intruder",
        is_admin=False,
    )
    runtime = await _build_runtime(tmp_path, user)
    try:
        project = await runtime.project_repo.create_project(
            "Locked Project", owner_id="usr_owner"
        )
        await runtime.artifact_repo.save_pending_chat_action(
            PendingChatAction(
                id="act_locked",
                session_id="sess-chat",
                user_id=user.id,
                project_id=project.id,
                action=ChatAction.REMOVE_TEST_CASE,
                payload={"plan_id": "plan_x", "test_case_id": "tc_x"},
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )

        response = await runtime.client.post(
            "/chat/sess-chat/confirm",
            json={"confirmed": True, "action_id": "act_locked"},
        )

        assert response.status_code == 401
        assert response.json()["error_code"] == "AUTH_ERROR"
    finally:
        await runtime.close()
