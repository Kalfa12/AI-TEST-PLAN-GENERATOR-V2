from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.copilot import CopilotAgent, CopilotReply
from ai_testplan_generator.llm.base import ChatMessage, ModelRole
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import DetailLevel, TestPlan as PlanModel
from tests.conftest import MockLLMGateway, make_test_case


class RecordingCopilotLLM(MockLLMGateway):
    def __init__(self) -> None:
        super().__init__()
        self.last_messages: Sequence[ChatMessage] = []

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
        self.last_messages = messages
        if schema is CopilotReply:
            return schema(message="The latest plan is available in context.")
        raise AssertionError(f"Unexpected schema: {schema.__name__}")


@pytest.mark.asyncio
async def test_copilot_includes_generated_plan_context() -> None:
    llm = RecordingCopilotLLM()
    memory = MemoryManager(llm=llm)
    test_case = make_test_case(
        title="Verify retry on transient failure",
        requirement_ids=["req_retry"],
    )
    plan = PlanModel(
        id="plan_latest",
        project_id="project-a",
        title="Retry Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Retry behavior",
        strategy="Exercise transient failure recovery.",
        test_cases=[test_case],
        coverage_matrix={"req_retry": [test_case.id]},
    )
    await memory.register_test_plan(plan)

    agent = CopilotAgent(
        AgentContext(
            llm=llm,
            memory=memory,
            session_id="session-a",
            project_id="project-a",
        )
    )

    await agent.run(CopilotAgent.Input(user_message="What test cases exist?"))

    prompt_text = "\n\n".join(message.content for message in llm.last_messages)
    assert "Generated project artefacts available to the assistant" in prompt_text
    assert "plan_latest: Retry Plan" in prompt_text
    assert "Verify retry on transient failure" in prompt_text
    assert "coverage=1/1 (100%)" in prompt_text
