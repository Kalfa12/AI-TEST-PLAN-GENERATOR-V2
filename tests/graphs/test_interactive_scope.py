from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.graphs.interactive import build_interactive_graph
from ai_testplan_generator.llm import ChatMessage, ModelRole
from ai_testplan_generator.memory.manager import MemoryManager
from tests.conftest import MockLLMGateway


class MutatingCopilotLLM(MockLLMGateway):
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
        return schema(
            message="I can add that test case.",
            proposed_action="add_test_case",
            action_payload={"title": "New overload test"},
            needs_confirmation=True,
        )


@pytest.mark.asyncio
async def test_interactive_graph_does_not_surface_fake_chat_mutations() -> None:
    llm = MutatingCopilotLLM()
    memory = MemoryManager(llm=llm)
    ctx = AgentContext(
        llm=llm,
        memory=memory,
        session_id="session-chat",
        project_id="project-a",
    )

    out = await build_interactive_graph(ctx).ainvoke(
        {
            "session_id": "session-chat",
            "project_id": "project-a",
            "user_message": "Add a new overload test case.",
        }
    )

    assert out["pending_action"] is None
    assert out["unsupported_action"] == "add_test_case"
    assert "missing persisted project/user context" in out["assistant_message"]
