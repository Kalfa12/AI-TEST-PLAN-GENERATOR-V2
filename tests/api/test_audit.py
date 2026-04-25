"""Tests for the audit logging middleware (M15)."""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api.deps import (
    get_brain,
    get_blob_store,
    get_current_user,
    get_event_broker,
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
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


@pytest.fixture
def audit_settings(tmp_path):  # type: ignore[no-untyped-def]
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
async def audit_client(mock_llm, audit_settings, tmp_path):  # type: ignore[no-untyped-def]
    from ai_testplan_generator.pipelines.brain import Brain

    test_brain = Brain.build(llm=mock_llm, settings=audit_settings)  # type: ignore[arg-type]
    blob_store = LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))
    project_repo = await ProjectRepository.create(db_path=str(tmp_path / "app.db"))
    _user_repo = await UserRepository.create(db_path=str(tmp_path / "app.db"))
    stub_user = User(id="usr_audit0001", email="a@test.local", display_name="A", is_admin=True)

    app = create_app(settings=audit_settings)
    app.dependency_overrides[get_brain] = lambda: test_brain
    app.dependency_overrides[get_settings] = lambda: audit_settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_user_repo] = lambda: _user_repo
    app.dependency_overrides[get_current_user] = lambda: stub_user
    app.dependency_overrides[get_event_broker] = lambda: InMemoryEventBroker()
    app.dependency_overrides[get_jobs] = lambda: {}
    app.dependency_overrides[get_plans] = lambda: {}
    app.dependency_overrides[get_project_plans] = lambda: {}

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c, audit_settings.app_db_path

    await project_repo.close()
    await _user_repo.close()


async def _count_audit_rows(db_path: str, method_path_prefix: str) -> int:
    async with aiosqlite.connect(db_path) as conn:
        # Table may not exist yet if no mutating requests have been made.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'"
        ) as cur:
            if await cur.fetchone() is None:
                return 0
        async with conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action LIKE ?",
            (f"%{method_path_prefix}%",),
        ) as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def test_post_creates_audit_row(audit_client) -> None:  # type: ignore[no-untyped-def]
    client, db_path = audit_client

    r = await client.post("/projects", json={"name": "audit-test-project"})
    assert r.status_code == 201

    # Give the fire-and-forget task a moment to write.
    await asyncio.sleep(0.15)

    count = await _count_audit_rows(db_path, "POST")
    assert count >= 1


async def test_get_does_not_create_audit_row(audit_client) -> None:  # type: ignore[no-untyped-def]
    client, db_path = audit_client

    await client.get("/healthz")

    await asyncio.sleep(0.15)

    # GET /healthz should not be audited.
    count = await _count_audit_rows(db_path, "GET:/healthz")
    assert count == 0


async def test_delete_creates_audit_row(audit_client) -> None:  # type: ignore[no-untyped-def]
    client, db_path = audit_client

    create_r = await client.post("/projects", json={"name": "to-delete"})
    project_id = create_r.json()["id"]

    await client.delete(f"/projects/{project_id}")
    await asyncio.sleep(0.15)

    count = await _count_audit_rows(db_path, "DELETE")
    assert count >= 1
