from __future__ import annotations

import pytest

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.planner import PlannerAgent
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import DetailLevel, TestPlan as PlanModel
from tests.conftest import MockLLMGateway, make_test_case


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
