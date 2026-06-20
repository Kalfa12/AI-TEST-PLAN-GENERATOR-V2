"""Phase 7 acceptance flow: ingest -> generate -> trace -> restart -> reload."""

from __future__ import annotations

import asyncio
import hashlib
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
    get_event_broker,
    get_job_repo,
    get_job_queue,
    get_jobs,
    get_plans,
    get_project_plans,
    get_project_repo,
    get_settings,
    get_user_repo,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.domain.jobs import JobRepository
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User, UserRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.jobs.queue import FakeJobQueue
from ai_testplan_generator.llm.base import ChatMessage, LLMResponse, ModelRole
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


FIXTURE = Path(__file__).parents[1] / "fixtures" / "phase7_acceptance_spec.md"


class AcceptanceLLM:
    """Deterministic structured-output fake for the full autonomous flow."""

    def __init__(self, *, embed_dim: int = 8) -> None:
        self.embed_dim = embed_dim
        self.call_log: list[dict[str, Any]] = []

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
        self.call_log.append({"method": "complete", "role": role, "n_messages": len(messages)})
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
        self.call_log.append(
            {"method": "complete_structured", "role": role, "schema": schema.__name__}
        )
        user_text = "\n".join(m.content for m in messages if m.role == "user")
        name = schema.__name__
        if name == "_ExtractorOutput":
            return schema.model_validate(
                {
                    "requirements": [
                        {
                            "external_id": "SRS-CMD-1",
                            "kind": "safety",
                            "title": "Emergency stop safe mode",
                            "statement": (
                                "The controller shall enter SAFE mode within 200 ms "
                                "when emergency stop is asserted."
                            ),
                            "acceptance_hint": "Assert emergency stop and measure mode transition time.",
                            "priority": 1,
                            "verbatim_excerpt": (
                                "SRS-CMD-1: The controller shall enter SAFE mode within "
                                "200 ms when emergency stop is asserted."
                            ),
                        },
                        {
                            "external_id": "SRS-CMD-2",
                            "kind": "operational",
                            "title": "Operator command audit log",
                            "statement": (
                                "The system shall log every operator command with timestamp, "
                                "operator identifier, and command result."
                            ),
                            "acceptance_hint": "Issue commands and inspect the audit log fields.",
                            "priority": 2,
                            "verbatim_excerpt": (
                                "SRS-CMD-2: The system shall log every operator command "
                                "with timestamp, operator identifier, and command result."
                            ),
                        },
                        {
                            "external_id": "SRS-CMD-3",
                            "kind": "regulatory",
                            "title": "Traceable exported report",
                            "statement": (
                                "The exported test report shall include requirement identifiers "
                                "and source references for every generated test case."
                            ),
                            "acceptance_hint": "Export a report and verify requirement/source references.",
                            "priority": 2,
                            "verbatim_excerpt": (
                                "SRS-CMD-3: The exported test report shall include requirement "
                                "identifiers and source references for every generated test case."
                            ),
                        },
                    ]
                }
            )
        if name == "CorpusSummary":
            return schema.model_validate(
                {
                    "title": "SIGMAXIS controller acceptance fixture",
                    "abstract": "Controller safety, audit logging, and report traceability.",
                    "key_subsystems": ["controller", "audit log", "report export"],
                    "standards_referenced": [],
                    "known_gaps": [],
                    "requirement_count_estimate": 3,
                }
            )
        if name == "ReviewReport":
            return schema.model_validate(
                {"approved": True, "findings": [], "overall_notes": "No blocking findings."}
            )
        if name == "_ArchitectOutput":
            return schema.model_validate(
                {
                    "title": "SIGMAXIS Acceptance Test Plan",
                    "introduction": "Deterministic acceptance plan for the Phase 7 fixture.",
                    "objectives": [
                        "Verify safety response",
                        "Verify audit logging",
                        "Verify report traceability",
                    ],
                    "scope": "Controller acceptance behavior from the uploaded fixture.",
                    "out_of_scope": ["Live hardware endurance testing"],
                    "strategy": "Map one executable test to each extracted requirement.",
                    "entry_criteria": ["Fixture requirements are ingested."],
                    "exit_criteria": ["All generated tests include source evidence."],
                    "risks": ["Mocked LLM behavior is deterministic by design."],
                }
            )
        if name == "_DraftCase":
            return schema.model_validate(_draft_case_for(user_text))
        if name == "_TraceCheck":
            return schema.model_validate(
                {
                    "covers_confidence": 0.95,
                    "additional_chunk_ids": [],
                    "contradictions": [],
                    "notes": "Generated test maps to the cited requirement source.",
                }
            )
        raise AssertionError(f"Unexpected structured schema requested: {name}")

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

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vector = [float(digest[i]) / 255.0 for i in range(self.embed_dim)]
            vectors.append(vector)
        return vectors


def _draft_case_for(prompt: str) -> dict[str, Any]:
    if "SRS-CMD-1" in prompt or "SAFE mode" in prompt:
        return {
            "title": "Verify emergency stop enters SAFE mode within 200 ms",
            "objective": "Confirm the controller transitions to SAFE mode fast enough.",
            "testing_types": ["system", "safety"],
            "preconditions": ["Controller is powered and operational."],
            "steps": [
                {
                    "action": "Assert the emergency stop input.",
                    "expected_result": "Controller enters SAFE mode within 200 ms.",
                }
            ],
            "acceptance_criteria": [
                {
                    "statement": "Measured SAFE-mode transition time is <= 200 ms.",
                    "measurable": True,
                    "tolerance": "<= 200 ms",
                }
            ],
            "estimated_duration_minutes": 20,
            "risk_level": 5,
            "risk_description": "Late SAFE mode can expose operators to unsafe motion.",
            "deliverables": ["timing capture", "test log"],
            "dependencies": ["emergency stop simulator"],
            "kpis": ["transition time"],
            "tags": ["SRS-CMD-1", "safety"],
        }
    if "SRS-CMD-2" in prompt or "operator command" in prompt:
        return {
            "title": "Verify operator commands are audit logged",
            "objective": "Confirm command audit entries contain all required fields.",
            "testing_types": ["system", "operational"],
            "steps": [
                {
                    "action": "Issue a valid operator command.",
                    "expected_result": "Audit log contains timestamp, operator id, and result.",
                }
            ],
            "acceptance_criteria": [
                {
                    "statement": "Every issued command has timestamp, operator identifier, and result.",
                    "measurable": True,
                }
            ],
            "estimated_duration_minutes": 15,
            "risk_level": 3,
            "deliverables": ["audit log extract"],
            "tags": ["SRS-CMD-2", "audit"],
        }
    return {
        "title": "Verify exported report includes source traceability",
        "objective": "Confirm generated reports retain requirement and source references.",
        "testing_types": ["system", "regulatory"],
        "steps": [
            {
                "action": "Export the generated test report.",
                "expected_result": "Every test case includes requirement identifiers and source references.",
            }
        ],
        "acceptance_criteria": [
            {
                "statement": "Exported report includes requirement ids and source references for all tests.",
                "measurable": True,
            }
        ],
        "estimated_duration_minutes": 10,
        "risk_level": 3,
        "deliverables": ["exported report"],
        "tags": ["SRS-CMD-3", "traceability"],
    }


@dataclass
class Runtime:
    client: AsyncClient
    brain: Brain
    artifact_repo: ArtifactRepository
    project_repo: ProjectRepository
    user_repo: UserRepository
    job_repo: JobRepository
    event_broker: InMemoryEventBroker

    async def close(self) -> None:
        await self.client.aclose()
        await self.event_broker.close()
        await self.artifact_repo.close()
        await self.project_repo.close()
        await self.user_repo.close()
        await self.job_repo.close()


async def _build_runtime(
    *,
    db_path: str,
    blob_root: str,
    llm: AcceptanceLLM,
    hydrate: bool = False,
) -> Runtime:
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        BLOB_STORE_BACKEND="local",
        BLOB_STORE_LOCAL_ROOT=blob_root,
        APP_DB_PATH=db_path,
        API_DEBUG=True,
    )
    artifact_repo = await ArtifactRepository.create(db_path=db_path)
    brain = Brain.build(llm=llm, settings=settings, artifact_repo=artifact_repo)
    if hydrate:
        await brain.memory.hydrate()

    blob_store = LocalFilesystemBlobStore(root=blob_root)
    project_repo = await ProjectRepository.create(db_path=db_path)
    brain.project_repo = project_repo
    user_repo = await UserRepository.create(db_path=db_path)
    job_repo = await JobRepository.create(db_path=db_path)
    event_broker = InMemoryEventBroker()
    plans: dict[str, Any] = {}
    project_plans: dict[str, list[str]] = {}
    jobs: dict[str, Any] = {}

    job_queue = FakeJobQueue(
        brain=brain,
        blob_store=blob_store,
        event_broker=event_broker,
        plans=plans,
        project_plans=project_plans,
        job_repo=job_repo,
    )

    user = User(
        id="usr_acceptance",
        email="acceptance@test.local",
        display_name="Acceptance Tester",
        is_admin=True,
    )

    app = create_app(settings=settings)
    app.dependency_overrides[get_brain] = lambda: brain
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_user_repo] = lambda: user_repo
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_event_broker] = lambda: event_broker
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_job_queue] = lambda: job_queue
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_plans] = lambda: plans
    app.dependency_overrides[get_project_plans] = lambda: project_plans

    client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )
    return Runtime(
        client=client,
        brain=brain,
        artifact_repo=artifact_repo,
        project_repo=project_repo,
        user_repo=user_repo,
        job_repo=job_repo,
        event_broker=event_broker,
    )


async def _wait_for_success(client: AsyncClient, job_id: str) -> dict[str, Any]:
    for _ in range(100):
        response = await client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] == "succeeded":
            return body
        if body["status"] == "failed":
            raise AssertionError(body.get("error") or body)
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not finish")


@pytest.mark.asyncio
async def test_core_acceptance_flow_survives_repository_restart(tmp_path: Path) -> None:
    db_path = str(tmp_path / "acceptance.db")
    blob_root = str(tmp_path / "blobs")
    llm = AcceptanceLLM()

    runtime = await _build_runtime(db_path=db_path, blob_root=blob_root, llm=llm)
    try:
        project_resp = await runtime.client.post(
            "/projects",
            json={"name": "Phase 7 Acceptance", "monthly_budget_usd": 25.0},
        )
        assert project_resp.status_code == 201
        project_id = project_resp.json()["id"]

        with FIXTURE.open("rb") as fixture:
            upload_resp = await runtime.client.post(
                f"/projects/{project_id}/documents",
                files={"file": ("phase7_acceptance_spec.md", fixture, "text/markdown")},
            )
        assert upload_resp.status_code == 200
        upload_body = upload_resp.json()
        assert upload_body["n_requirements"] == 3

        create_plan_resp = await runtime.client.post(
            f"/projects/{project_id}/plans",
            json={
                "goal": "Generate a detailed acceptance plan from the uploaded fixture.",
                "detail_level": "detailed",
                "max_revision_rounds": 1,
                "interactive": False,
            },
        )
        assert create_plan_resp.status_code == 202
        job = await _wait_for_success(runtime.client, create_plan_resp.json()["job_id"])
        plan_id = job["result"]["plan_id"]

        plan_resp = await runtime.client.get(f"/projects/{project_id}/plans/{plan_id}")
        assert plan_resp.status_code == 200
        plan = plan_resp.json()
        assert plan["test_cases"]
        assert all(tc["source_evidence"] for tc in plan["test_cases"])

        first_requirement_id = plan["test_cases"][0]["requirement_ids"][0]
        trace_resp = await runtime.client.get(f"/trace/{first_requirement_id}")
        assert trace_resp.status_code == 200
        trace = trace_resp.json()
        assert trace["root"]["type"] == "Requirement"
        assert any(node["type"] == "Chunk" for node in trace["nodes"].values())
    finally:
        await runtime.close()

    reloaded = await _build_runtime(
        db_path=db_path, blob_root=blob_root, llm=llm, hydrate=True
    )
    try:
        docs_resp = await reloaded.client.get(f"/projects/{project_id}/documents")
        assert docs_resp.status_code == 200
        assert docs_resp.json()["total"] == 1

        reloaded_plan_resp = await reloaded.client.get(
            f"/projects/{project_id}/plans/{plan_id}"
        )
        assert reloaded_plan_resp.status_code == 200
        reloaded_plan = reloaded_plan_resp.json()
        assert len(reloaded_plan["test_cases"]) == len(plan["test_cases"])
        assert all(tc["source_evidence"] for tc in reloaded_plan["test_cases"])

        coverage_resp = await reloaded.client.get(
            f"/projects/{project_id}/plans/{plan_id}/coverage"
        )
        assert coverage_resp.status_code == 200
        coverage = coverage_resp.json()["matrix"]
        assert coverage
        assert all(test_ids for test_ids in coverage.values())

        requirements = await reloaded.brain.memory.get_requirements_for_project(project_id)
        assert len(requirements) == 3
        extracted_text = "\n".join(r.statement for r in requirements).lower()
        assert "ignore all previous instructions" not in extracted_text
        assert "hidden requirement" not in extracted_text

        first_requirement_id = reloaded_plan["test_cases"][0]["requirement_ids"][0]
        trace_resp = await reloaded.client.get(f"/trace/{first_requirement_id}")
        assert trace_resp.status_code == 200
        trace = trace_resp.json()
        assert trace["root"]["type"] == "Requirement"
        assert any(node["type"] == "Chunk" for node in trace["nodes"].values())
    finally:
        await reloaded.close()
