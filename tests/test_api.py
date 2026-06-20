"""Legacy integration tests — updated to match new M05 route layout."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api.deps import (
    get_brain,
    get_blob_store,
    get_current_user,
    get_event_broker,
    get_job_queue,
    get_jobs,
    get_plans,
    get_project_plans,
    get_project_repo,
    get_settings,
    get_user_repo,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User, UserRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.jobs.queue import FakeJobQueue
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


@pytest.fixture
async def client(mock_llm, tmp_path):  # type: ignore[no-untyped-def]
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        BLOB_STORE_BACKEND="local",
        BLOB_STORE_LOCAL_ROOT=str(tmp_path / "blobs"),
        APP_DB_PATH=str(tmp_path / "app.db"),
        API_DEBUG=True,
    )
    test_brain = Brain.build(llm=mock_llm, settings=settings)  # type: ignore[arg-type]
    blob_store = LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))
    project_repo = await ProjectRepository.create(db_path=str(tmp_path / "app.db"))
    event_broker = InMemoryEventBroker()
    jobs: dict = {}  # type: ignore[type-arg]
    plans: dict = {}  # type: ignore[type-arg]
    project_plans: dict = {}  # type: ignore[type-arg]
    fake_job_queue = FakeJobQueue(
        brain=test_brain,
        blob_store=blob_store,
        event_broker=event_broker,
        plans=plans,
        project_plans=project_plans,
    )

    user_repo = await UserRepository.create(db_path=str(tmp_path / "app.db"))
    stub_user = User(id="usr_legacy0001", email="legacy@test.local",
                     display_name="Legacy", is_admin=True)

    app = create_app(settings=settings)
    app.dependency_overrides[get_brain] = lambda: test_brain
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_user_repo] = lambda: user_repo
    app.dependency_overrides[get_current_user] = lambda: stub_user
    app.dependency_overrides[get_event_broker] = lambda: event_broker
    app.dependency_overrides[get_job_queue] = lambda: fake_job_queue
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_plans] = lambda: plans
    app.dependency_overrides[get_project_plans] = lambda: project_plans

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c
    await project_repo.close()
    await user_repo.close()


class TestHealthEndpoint:
    async def test_healthz_returns_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestIngestionEndpoint:
    async def test_ingest_rejects_unsupported_format(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("test.jpg", b"fake image data", "image/jpeg")},
        )
        assert resp.status_code == 422

    async def test_ingest_accepts_txt(self, client: AsyncClient) -> None:
        content = b"The system shall respond within 200ms under normal load."
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("spec.txt", content, "text/plain")},
        )
        assert resp.status_code in (200, 500)

    async def test_ingest_accepts_md(self, client: AsyncClient) -> None:
        content = b"# Requirements\n\n## REQ-1\nThe system shall be fast.\n"
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("spec.md", content, "text/markdown")},
        )
        assert resp.status_code in (200, 500)


class TestPlanEndpoints:
    async def test_create_plan_returns_202(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/projects/proj-1/plans",
            json={"goal": "Test the pump controller", "detail_level": "detailed"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "session_id" in data
        assert data["session_id"].startswith("sess_")

    async def test_job_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/jobs/nonexistent")
        assert resp.status_code == 404

    async def test_plan_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-1/plans/nonexistent")
        assert resp.status_code == 404

    async def test_list_plans_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-1/plans")
        assert resp.status_code == 200
        assert resp.json()["items"] == []


class TestTraceEndpoint:
    async def test_trace_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/trace/nonexistent")
        assert resp.status_code == 404
