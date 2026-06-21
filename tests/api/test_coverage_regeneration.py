"""Phase 10: coverage-driven single-requirement regeneration."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_current_user,
    get_defects,
    get_plans,
    get_project_repo,
    get_settings,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.llm.base import ChatMessage, LLMResponse, ModelRole
from ai_testplan_generator.models import DetailLevel, TestPlan as PlanModel
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore
from tests.conftest import make_chunk, make_document, make_requirement, make_section


class CoverageRepairLLM:
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
        if schema.__name__ == "_DraftCase":
            return schema(
                title="Generated over-temperature shutdown test",
                objective="Verify the controller shuts down safely when over-temperature is detected.",
                testing_types=["system", "safety"],
                steps=[
                    {
                        "action": "Raise the simulated board temperature above the shutdown threshold.",
                        "expected_result": "The controller disables the actuator and reports an over-temperature fault.",
                    }
                ],
                acceptance_criteria=[
                    {
                        "statement": "The actuator is disabled and the fault is reported within 1 second.",
                        "measurable": True,
                    }
                ],
                risk_level=4,
                tags=["coverage-repair", "safety"],
            )
        if schema.__name__ == "_TraceCheck":
            return schema(
                covers_confidence=0.95,
                additional_chunk_ids=[],
                contradictions=[],
                notes="Generated test directly verifies the requirement.",
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
class CoverageRepairRuntime:
    client: AsyncClient
    brain: Brain
    artifact_repo: ArtifactRepository
    project_repo: ProjectRepository
    db_path: str

    async def close(self) -> None:
        await self.client.aclose()
        await self.artifact_repo.close()
        await self.project_repo.close()


async def _build_runtime(tmp_path: Path) -> CoverageRepairRuntime:
    db_path = str(tmp_path / "app.db")
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        BLOB_STORE_BACKEND="local",
        BLOB_STORE_LOCAL_ROOT=str(tmp_path / "blobs"),
        APP_DB_PATH=db_path,
        API_DEBUG=True,
    )
    artifact_repo = await ArtifactRepository.create(db_path=db_path)
    brain = Brain.build(
        llm=CoverageRepairLLM(),
        settings=settings,
        artifact_repo=artifact_repo,
    )
    project_repo = await ProjectRepository.create(db_path=db_path)
    brain.project_repo = project_repo
    blob_store = LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))
    plans: dict[str, PlanModel] = {}
    defects: dict[str, Any] = {}
    user = User(
        id="usr_phase10",
        email="phase10@test.local",
        display_name="Phase 10",
        is_admin=True,
    )

    app = create_app(settings=settings)
    app.dependency_overrides[get_brain] = lambda: brain
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_plans] = lambda: plans
    app.dependency_overrides[get_defects] = lambda: defects

    client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )
    return CoverageRepairRuntime(
        client=client,
        brain=brain,
        artifact_repo=artifact_repo,
        project_repo=project_repo,
        db_path=db_path,
    )


async def _seed_uncovered_requirement(runtime: CoverageRepairRuntime) -> str:
    doc = make_document(project_id="proj_repair", title="Controller Spec")
    section = make_section(doc.id)
    chunk = make_chunk(
        doc.id,
        section.id,
        text="The controller shall disable the actuator when board temperature exceeds 90 C.",
    )
    requirement = make_requirement(
        "proj_repair",
        statement="The controller shall disable the actuator when board temperature exceeds 90 C.",
        source_chunk_ids=[chunk.id],
        source_document_id=doc.id,
    )
    plan = PlanModel(
        id="plan_repair",
        project_id="proj_repair",
        title="Controller Qualification",
        detail_level=DetailLevel.DETAILED,
        scope="Controller safety behavior.",
        strategy="Cover every extracted safety requirement.",
        coverage_matrix={requirement.id: []},
    )

    await runtime.brain.memory.register_document(doc)
    await runtime.brain.memory.register_sections([section])
    await runtime.brain.memory.register_chunks([chunk])
    await runtime.brain.memory.register_requirements([requirement])
    await runtime.brain.memory.register_test_plan(plan)
    return requirement.id


@pytest.mark.asyncio
async def test_generate_requirement_test_case_repairs_coverage(tmp_path: Path) -> None:
    runtime = await _build_runtime(tmp_path)
    try:
        requirement_id = await _seed_uncovered_requirement(runtime)

        response = await runtime.client.post(
            f"/projects/proj_repair/plans/plan_repair/requirements/{requirement_id}/test-case",
            json={},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["requirement_id"] == requirement_id
        assert body["test_case"]["title"] == "Generated over-temperature shutdown test"
        assert body["test_case"]["requirement_ids"] == [requirement_id]
        assert body["test_case"]["source_evidence"][0]["chunk_id"].startswith("ch_")
        assert body["coverage_matrix"][requirement_id] == [body["test_case"]["id"]]

        reloaded = await runtime.artifact_repo.get_test_plan("plan_repair")
        assert reloaded is not None
        assert len(reloaded.test_cases) == 1
        assert reloaded.coverage_matrix[requirement_id] == [reloaded.test_cases[0].id]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_generate_requirement_test_case_survives_repository_reload(
    tmp_path: Path,
) -> None:
    runtime = await _build_runtime(tmp_path)
    try:
        requirement_id = await _seed_uncovered_requirement(runtime)

        response = await runtime.client.post(
            f"/projects/proj_repair/plans/plan_repair/requirements/{requirement_id}/test-case",
            json={},
        )
        assert response.status_code == 200
    finally:
        await runtime.close()

    repo = await ArtifactRepository.create(db_path=str(tmp_path / "app.db"))
    try:
        reloaded = await repo.get_test_plan("plan_repair")
        assert reloaded is not None
        assert len(reloaded.test_cases) == 1
        assert reloaded.coverage_matrix[requirement_id] == [reloaded.test_cases[0].id]
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_generate_requirement_test_case_rejects_other_project_requirement(
    tmp_path: Path,
) -> None:
    runtime = await _build_runtime(tmp_path)
    try:
        await _seed_uncovered_requirement(runtime)
        other_doc = make_document(project_id="proj_other", title="Other Spec")
        other_req = make_requirement(
            "proj_other",
            statement="The unrelated system shall expose diagnostics.",
            source_document_id=other_doc.id,
        )
        await runtime.brain.memory.register_document(other_doc)
        await runtime.brain.memory.register_requirements([other_req])

        response = await runtime.client.post(
            f"/projects/proj_repair/plans/plan_repair/requirements/{other_req.id}/test-case",
            json={},
        )

        assert response.status_code == 404
        reloaded = await runtime.artifact_repo.get_test_plan("plan_repair")
        assert reloaded is not None
        assert reloaded.test_cases == []
    finally:
        await runtime.close()
