from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.agents.test_generator import TestGeneratorAgent as GeneratorAgent
from ai_testplan_generator.domain.projects import Project, ProjectIndustry
from ai_testplan_generator.ingestion.extraction import RequirementExtractor
from ai_testplan_generator.llm.base import ChatMessage, ModelRole
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import DetailLevel
from ai_testplan_generator.models.defects import (
    DefectType,
    defect_catalog_for_industry,
    industry_standard_refs,
)
from tests.conftest import (
    MockLLMGateway,
    make_chunk,
    make_document,
    make_requirement,
    make_section,
)


class FakeProjectRepo:
    def __init__(self, project: Project) -> None:
        self.project = project

    async def get_project(self, project_id: str) -> Project | None:
        if project_id == self.project.id:
            return self.project
        return None


class RecordingIndustryLLM(MockLLMGateway):
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
        if schema.__name__ == "_DraftCase":
            return schema(
                title="Verify flight-control limit",
                objective="Verify the limit is enforced.",
                steps=[
                    {
                        "action": "Command the system beyond the certified limit.",
                        "expected_result": "The command is rejected.",
                    }
                ],
                acceptance_criteria=[
                    {"statement": "The command is rejected.", "measurable": True}
                ],
                risk_level=4,
            )
        if schema.__name__ == "_ExtractorOutput":
            return schema(requirements=[])
        raise AssertionError(f"Unexpected schema: {schema.__name__}")


async def _generator_with_project_industry(
    industry: ProjectIndustry,
) -> tuple[GeneratorAgent, RecordingIndustryLLM, Any]:
    llm = RecordingIndustryLLM()
    memory = MemoryManager(llm=llm)
    document = make_document(project_id="project-a", title="Control Specification")
    section = make_section(document.id, title="Limits")
    chunk = make_chunk(
        document.id,
        section.id,
        text="The controller shall reject commands beyond the certified limit.",
    )
    requirement = make_requirement(
        project_id="project-a",
        statement="The controller shall reject commands beyond the certified limit.",
        source_chunk_ids=[chunk.id],
        source_document_id=document.id,
    )
    await memory.register_document(document)
    await memory.register_sections([section])
    await memory.register_chunks([chunk])
    await memory.register_requirements([requirement])
    project_repo = FakeProjectRepo(
        Project(id="project-a", name="Project A", industry=industry)
    )
    ctx = AgentContext(
        llm=llm,
        memory=memory,
        session_id="session-a",
        project_id="project-a",
        project_repo=project_repo,
    )
    return GeneratorAgent(ctx), llm, requirement


@pytest.mark.asyncio
async def test_generator_prompt_includes_project_industry_block() -> None:
    agent, llm, requirement = await _generator_with_project_industry(
        ProjectIndustry.AEROSPACE
    )

    await agent.invoke(
        GeneratorAgent.Input(
            requirements=[requirement],
            detail_level=DetailLevel.DETAILED,
        )
    )

    system_prompt = "\n".join(m.content for m in llm.last_messages if m.role == "system")
    assert "PROJECT INDUSTRY CONTEXT" in system_prompt
    assert "Industry: aerospace" in system_prompt
    assert "DO-178C" in system_prompt
    assert "traceability_gap" in system_prompt


@pytest.mark.asyncio
async def test_requirement_extractor_prompt_accepts_industry_context() -> None:
    llm = RecordingIndustryLLM()
    document = make_document(project_id="project-med", title="Medical Device Spec")
    chunk = make_chunk(
        document.id,
        text="The device shall log therapy interruption events.",
    )
    extractor = RequirementExtractor(
        llm,
        project_id="project-med",
        industry=ProjectIndustry.MEDICAL.value,
    )

    await extractor.extract_from_chunk(chunk)

    system_prompt = "\n".join(m.content for m in llm.last_messages if m.role == "system")
    assert "Industry: medical" in system_prompt
    assert "IEC 62304" in system_prompt
    assert "ISO 14971" in system_prompt


def test_defect_catalog_prioritizes_industry_specific_entries() -> None:
    assert "ISO 26262" in industry_standard_refs("automotive")
    automotive_catalog = defect_catalog_for_industry("automotive")
    assert automotive_catalog[0].id == DefectType.MISSING_RISK_ANALYSIS
