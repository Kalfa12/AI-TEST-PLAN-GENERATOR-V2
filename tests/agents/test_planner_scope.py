from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest
from pydantic import BaseModel

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.planner import PlannerAgent
from ai_testplan_generator.llm.base import ChatMessage, ModelRole
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import (
    DetailLevel,
    Resource,
    TestCaseStatus as CaseStatus,
    TestPlan as PlanModel,
)
from tests.conftest import MockLLMGateway, make_test_case


class PlanningDraftLLM(MockLLMGateway):
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
        self.call_log.append({"method": "complete_structured", "schema": schema.__name__})
        return schema.model_validate(
            {
                "milestones": [
                    {
                        "name": "Bench execution",
                        "due": date(2099, 1, 7).isoformat(),
                        "gate": False,
                    }
                ],
                "assignments": [
                    {
                        "test_case_id": "tc_real",
                        "start": date(2099, 1, 2).isoformat(),
                        "end": date(2099, 1, 3).isoformat(),
                        "resource_ids": ["res_real", "res_fake"],
                        "service": "Validation lab",
                    },
                    {
                        "test_case_id": "tc_missing",
                        "start": date(2099, 1, 2).isoformat(),
                        "end": date(2099, 1, 3).isoformat(),
                        "resource_ids": ["res_real"],
                    },
                ],
            }
        )


@pytest.mark.asyncio
async def test_planner_skips_assignment_when_no_resources_configured() -> None:
    llm = MockLLMGateway()
    memory = MemoryManager(llm=llm)
    ctx = AgentContext(
        llm=llm,
        memory=memory,
        session_id="session-planner",
        project_id="project-a",
    )
    plan = PlanModel(
        project_id="project-a",
        title="Scope-limited plan",
        detail_level=DetailLevel.DETAILED,
        scope="Controller overload tests",
        strategy="Run requirement-driven functional tests.",
        test_cases=[make_test_case()],
    )

    schedule = await PlannerAgent(ctx).invoke(PlannerAgent.Input(plan=plan, resources=[]))

    assert schedule.plan_id == plan.id
    assert schedule.milestones == []
    assert schedule.assignments == {}
    assert not any(call["method"] == "complete_structured" for call in llm.call_log)


@pytest.mark.asyncio
async def test_planner_discards_fabricated_resource_ids() -> None:
    llm = PlanningDraftLLM()
    memory = MemoryManager(llm=llm)
    ctx = AgentContext(
        llm=llm,
        memory=memory,
        session_id="session-planner",
        project_id="project-a",
    )
    tc = make_test_case()
    tc.id = "tc_real"
    plan = PlanModel(
        project_id="project-a",
        title="Resource-backed plan",
        detail_level=DetailLevel.DETAILED,
        scope="Controller overload tests",
        strategy="Run requirement-driven functional tests.",
        test_cases=[tc],
    )
    resource = Resource(
        id="res_real",
        project_id="project-a",
        name="Validation bench",
        service="Validation lab",
        role="Technician",
    )

    schedule = await PlannerAgent(ctx).invoke(
        PlannerAgent.Input(plan=plan, resources=[resource])
    )

    assert list(schedule.assignments) == ["tc_real"]
    assert schedule.assignments["tc_real"].resource_ids == ["res_real"]
    assert plan.schedule == schedule
    assert plan.test_cases[0].status == CaseStatus.PLANNED
    assert plan.test_cases[0].assignee == "Validation bench"
