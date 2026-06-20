"""Project LLM budget enforcement at the agent boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_testplan_generator.agents.base import AgentContext, BaseAgent
from ai_testplan_generator.api.errors import BudgetExceededError
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.telemetry.cost import record_usage


class _EchoAgent(BaseAgent[str, str]):
    name = "echo"

    def __init__(self, ctx: AgentContext) -> None:
        super().__init__(ctx)
        self.ran = False

    async def run(self, inp: str) -> str:
        self.ran = True
        return inp


@pytest.mark.asyncio
async def test_agent_invoke_blocks_when_project_budget_is_exhausted(
    tmp_path: Path, mock_llm
) -> None:
    db_path = str(tmp_path / "app.db")
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        APP_DB_PATH=db_path,
    )
    project_repo = await ProjectRepository.create(db_path=db_path)
    try:
        project = await project_repo.create_project(
            "Budget Guard", monthly_budget_usd=0.001
        )
        await record_usage(
            db_path,
            session_id="sess-existing",
            project_id=project.id,
            user_id=None,
            model="gpt-4o",
            role="balanced",
            input_tokens=1000,
            output_tokens=500,
        )
        memory = MemoryManager(llm=mock_llm, settings=settings)
        ctx = AgentContext(
            llm=mock_llm,
            memory=memory,
            session_id="sess-budget",
            project_id=project.id,
            settings=settings,
            project_repo=project_repo,
        )
        agent = _EchoAgent(ctx)

        with pytest.raises(BudgetExceededError):
            await agent.invoke("blocked")

        assert agent.ran is False
    finally:
        await project_repo.close()


@pytest.mark.asyncio
async def test_agent_invoke_runs_when_project_is_under_budget(
    tmp_path: Path, mock_llm
) -> None:
    db_path = str(tmp_path / "app.db")
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        APP_DB_PATH=db_path,
    )
    project_repo = await ProjectRepository.create(db_path=db_path)
    try:
        project = await project_repo.create_project(
            "Budget Guard", monthly_budget_usd=5.0
        )
        memory = MemoryManager(llm=mock_llm, settings=settings)
        ctx = AgentContext(
            llm=mock_llm,
            memory=memory,
            session_id="sess-budget",
            project_id=project.id,
            settings=settings,
            project_repo=project_repo,
        )
        agent = _EchoAgent(ctx)

        assert await agent.invoke("allowed") == "allowed"
        assert agent.ran is True
    finally:
        await project_repo.close()
