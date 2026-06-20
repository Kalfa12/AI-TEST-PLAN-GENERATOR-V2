from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.test_generator import TestGeneratorAgent as GeneratorAgent
from ai_testplan_generator.llm import ChatMessage, ModelRole
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import DetailLevel
from tests.conftest import (
    MockLLMGateway,
    make_chunk,
    make_document,
    make_requirement,
    make_section,
)


class SuccessfulDraftLLM(MockLLMGateway):
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
        self.call_log.append(
            {"method": "complete_structured", "role": role, "schema": schema.__name__}
        )
        return schema(
            title="Verify overload alarm",
            objective="Confirm the alarm is raised for an overload condition.",
            steps=[
                {
                    "action": "Inject an overload condition.",
                    "expected_result": "The overload alarm is displayed within 2 seconds.",
                }
            ],
            acceptance_criteria=[
                {"statement": "Alarm appears within 2 seconds.", "measurable": True}
            ],
            risk_level=3,
        )


class FailingDraftLLM(MockLLMGateway):
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
        raise RuntimeError("LLM down")


async def _agent_with_memory(
    llm: MockLLMGateway,
) -> tuple[GeneratorAgent, Any, Any]:
    memory = MemoryManager(llm=llm)
    document = make_document(project_id="project-a", title="Alarm Specification")
    section = make_section(document.id, title="Alarm behavior")
    chunk = make_chunk(
        document.id,
        section.id,
        text="The controller shall raise an overload alarm within 2 seconds.",
    )
    requirement = make_requirement(
        project_id="project-a",
        statement="The controller shall raise an overload alarm within 2 seconds.",
        source_chunk_ids=[chunk.id],
        source_document_id=document.id,
    )
    await memory.register_document(document)
    await memory.register_sections([section])
    await memory.register_chunks([chunk])
    await memory.register_requirements([requirement])
    ctx = AgentContext(
        llm=llm,
        memory=memory,
        session_id="session-a",
        project_id="project-a",
    )
    return GeneratorAgent(ctx), requirement, chunk


@pytest.mark.asyncio
async def test_generator_stores_source_evidence_and_uses_feedback() -> None:
    llm = SuccessfulDraftLLM()
    agent, requirement, chunk = await _agent_with_memory(llm)

    out = await agent.invoke(
        GeneratorAgent.Input(
            requirements=[requirement],
            detail_level=DetailLevel.DETAILED,
            user_feedback=["Reviewer major finding: expected result must be measurable."],
        )
    )

    assert len(out.test_cases) == 1
    test_case = out.test_cases[0]
    assert test_case.source_evidence
    assert test_case.source_evidence[0].chunk_id == chunk.id
    assert test_case.source_evidence[0].document_id == chunk.document_id
    assert test_case.source_evidence[0].relation == "source"
    assert "overload alarm" in test_case.source_evidence[0].excerpt

    system_prompt = "\n".join(m.content for m in llm.last_messages if m.role == "system")
    assert "Reviewer major finding" in system_prompt
    assert "expected result must be measurable" in system_prompt


@pytest.mark.asyncio
async def test_generator_raises_when_all_requirements_fail() -> None:
    llm = FailingDraftLLM()
    agent, requirement, _chunk = await _agent_with_memory(llm)

    with pytest.raises(RuntimeError, match="produced no valid test cases"):
        await agent.invoke(GeneratorAgent.Input(requirements=[requirement]))
