"""Shared fixtures for API tests.

We bypass the FastAPI lifespan entirely by:
  1. Setting all required app.state values directly on the app object.
  2. Overriding FastAPI dependencies for the brain and settings.

This keeps tests fast (no real SQLite I/O for the episodic store) and
deterministic (mock LLM with canned responses).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api.deps import (
    get_brain,
    get_blob_store,
    get_event_broker,
    get_jobs,
    get_plans,
    get_project_plans,
    get_project_repo,
    get_settings,
)
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


@pytest.fixture
def api_settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    """In-memory backends + temp paths for file-based resources."""
    return Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        BLOB_STORE_BACKEND="local",
        BLOB_STORE_LOCAL_ROOT=str(tmp_path / "blobs"),
        APP_DB_PATH=str(tmp_path / "app.db"),
        API_DEBUG=True,
    )


@pytest_asyncio.fixture
async def client(mock_llm, api_settings, tmp_path):  # type: ignore[no-untyped-def]
    """AsyncClient with mock Brain and all app.state values pre-populated."""
    test_brain = Brain.build(llm=mock_llm, settings=api_settings)  # type: ignore[arg-type]
    blob_store = LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))
    project_repo = await ProjectRepository.create(
        db_path=str(tmp_path / "app.db")
    )
    event_broker = InMemoryEventBroker()
    jobs: dict = {}  # type: ignore[type-arg]
    plans: dict = {}  # type: ignore[type-arg]
    project_plans: dict = {}  # type: ignore[type-arg]

    app = create_app(settings=api_settings)

    # Override every dependency that reads from app.state so tests
    # work without running the lifespan.
    app.dependency_overrides[get_brain] = lambda: test_brain
    app.dependency_overrides[get_settings] = lambda: api_settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_event_broker] = lambda: event_broker
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_plans] = lambda: plans
    app.dependency_overrides[get_project_plans] = lambda: project_plans

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c

    await project_repo.close()
