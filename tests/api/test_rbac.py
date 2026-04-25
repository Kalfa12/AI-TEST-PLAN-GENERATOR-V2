"""Tests for RBAC enforcement (M14)."""

from __future__ import annotations

import pytest
import pytest_asyncio
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
from ai_testplan_generator.domain.projects import ProjectRepository, ProjectRole
from ai_testplan_generator.domain.users import User, UserRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.jobs.queue import FakeJobQueue
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


def _make_user(user_id: str, is_admin: bool = False) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@test.local",
        display_name=user_id,
        is_admin=is_admin,
    )


@pytest_asyncio.fixture
async def rbac_setup(mock_llm, tmp_path):  # type: ignore[no-untyped-def]
    """Returns (project_repo, user_repo, project_id) with one project pre-created."""
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        BLOB_STORE_BACKEND="local",
        BLOB_STORE_LOCAL_ROOT=str(tmp_path / "blobs"),
        APP_DB_PATH=str(tmp_path / "app.db"),
        API_DEBUG=True,
    )
    project_repo = await ProjectRepository.create(db_path=str(tmp_path / "app.db"))
    user_repo = await UserRepository.create(db_path=str(tmp_path / "app.db"))
    project = await project_repo.create_project(name="test-project")

    yield settings, project_repo, user_repo, project.id, mock_llm, tmp_path

    await project_repo.close()
    await user_repo.close()


def _build_client(
    mock_llm,  # type: ignore[no-untyped-def]
    settings: Settings,
    project_repo: ProjectRepository,
    user_repo: UserRepository,
    current_user: User,
    tmp_path,  # type: ignore[no-untyped-def]
) -> AsyncClient:
    from ai_testplan_generator.pipelines.brain import Brain

    test_brain = Brain.build(llm=mock_llm, settings=settings)  # type: ignore[arg-type]
    blob_store = LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))
    event_broker = InMemoryEventBroker()
    plans: dict = {}  # type: ignore[type-arg]
    project_plans: dict = {}  # type: ignore[type-arg]
    fake_jq = FakeJobQueue(
        brain=test_brain,
        blob_store=blob_store,
        event_broker=event_broker,
        plans=plans,
        project_plans=project_plans,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_brain] = lambda: test_brain
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_user_repo] = lambda: user_repo
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_event_broker] = lambda: event_broker
    app.dependency_overrides[get_job_queue] = lambda: fake_jq
    app.dependency_overrides[get_jobs] = lambda: {}
    app.dependency_overrides[get_plans] = lambda: plans
    app.dependency_overrides[get_project_plans] = lambda: project_plans
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


async def test_viewer_cannot_upload_document(rbac_setup) -> None:  # type: ignore[no-untyped-def]
    settings, project_repo, user_repo, project_id, mock_llm, tmp_path = rbac_setup

    viewer = _make_user("usr_viewer01")
    await project_repo.add_member(project_id, viewer.id, ProjectRole.VIEWER)

    async with _build_client(
        mock_llm, settings, project_repo, user_repo, viewer, tmp_path
    ) as c:
        r = await c.post(
            f"/projects/{project_id}/documents",
            files={"file": ("test.md", b"# hello", "text/markdown")},
        )
    assert r.status_code == 401  # AuthError maps to 401


async def test_editor_can_upload_document(rbac_setup) -> None:  # type: ignore[no-untyped-def]
    settings, project_repo, user_repo, project_id, mock_llm, tmp_path = rbac_setup

    editor = _make_user("usr_editor01")
    await project_repo.add_member(project_id, editor.id, ProjectRole.EDITOR)

    async with _build_client(
        mock_llm, settings, project_repo, user_repo, editor, tmp_path
    ) as c:
        r = await c.post(
            f"/projects/{project_id}/documents",
            files={"file": ("test.md", b"# hello", "text/markdown")},
        )
    # 200 (sync ingest) or 202 (background) — either means RBAC passed.
    assert r.status_code in (200, 202)


async def test_admin_can_upload_general_document(rbac_setup) -> None:  # type: ignore[no-untyped-def]
    settings, project_repo, user_repo, _project_id, mock_llm, tmp_path = rbac_setup

    admin = _make_user("usr_admin001", is_admin=True)

    async with _build_client(
        mock_llm, settings, project_repo, user_repo, admin, tmp_path
    ) as c:
        r = await c.post(
            "/general/documents",
            files={"file": ("test.md", b"# hello", "text/markdown")},
        )
    assert r.status_code != 401


async def test_non_member_cannot_generate_plan(rbac_setup) -> None:  # type: ignore[no-untyped-def]
    settings, project_repo, user_repo, project_id, mock_llm, tmp_path = rbac_setup

    outsider = _make_user("usr_nobody01")
    # Not added to the project.

    async with _build_client(
        mock_llm, settings, project_repo, user_repo, outsider, tmp_path
    ) as c:
        r = await c.post(
            f"/projects/{project_id}/plans",
            json={"goal": "test", "detail_level": "summary", "max_revision_rounds": 1},
        )
    assert r.status_code == 401
