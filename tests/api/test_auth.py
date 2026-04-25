"""Tests for the /auth/* endpoints (M13)."""

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
    get_user_repo,
)
from ai_testplan_generator.api.security.password import hash_password
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import UserRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


@pytest.fixture
def auth_settings(tmp_path):  # type: ignore[no-untyped-def]
    return Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        BLOB_STORE_BACKEND="local",
        BLOB_STORE_LOCAL_ROOT=str(tmp_path / "blobs"),
        APP_DB_PATH=str(tmp_path / "app.db"),
        API_DEBUG=True,
        JWT_SECRET="test-secret-for-auth-tests-minimum-32-bytes",
    )


@pytest_asyncio.fixture
async def auth_client(mock_llm, auth_settings, tmp_path):  # type: ignore[no-untyped-def]
    """Client wired to real UserRepository so auth flows work end-to-end."""
    from ai_testplan_generator.pipelines.brain import Brain

    test_brain = Brain.build(llm=mock_llm, settings=auth_settings)  # type: ignore[arg-type]
    blob_store = LocalFilesystemBlobStore(root=str(tmp_path / "blobs"))
    project_repo = await ProjectRepository.create(db_path=str(tmp_path / "app.db"))
    _user_repo = await UserRepository.create(db_path=str(tmp_path / "app.db"))
    event_broker = InMemoryEventBroker()

    # Pre-seed a test user.
    await _user_repo.create_user(
        email="admin@example.com",
        display_name="Admin",
        password_hash=hash_password("correct-password"),
    )

    app = create_app(settings=auth_settings)
    # Override all deps except get_current_user — auth tests exercise that path.
    app.dependency_overrides[get_brain] = lambda: test_brain
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_user_repo] = lambda: _user_repo
    app.dependency_overrides[get_event_broker] = lambda: event_broker
    app.dependency_overrides[get_jobs] = lambda: {}
    app.dependency_overrides[get_plans] = lambda: {}
    app.dependency_overrides[get_project_plans] = lambda: {}

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c

    await project_repo.close()
    await _user_repo.close()


async def test_login_correct_credentials(auth_client: AsyncClient) -> None:
    r = await auth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-password"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(auth_client: AsyncClient) -> None:
    r = await auth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )
    assert r.status_code == 401


async def test_login_unknown_email(auth_client: AsyncClient) -> None:
    r = await auth_client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "x"},
    )
    assert r.status_code == 401


async def test_me_without_token(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/auth/me")
    assert r.status_code == 401


async def test_me_with_valid_bearer(auth_client: AsyncClient) -> None:
    login = await auth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-password"},
    )
    token = login.json()["access_token"]

    r = await auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@example.com"


async def test_create_api_key(auth_client: AsyncClient) -> None:
    login = await auth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-password"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await auth_client.post(
        "/auth/api-keys", json={"name": "ci-key"}, headers=headers
    )
    assert r.status_code == 201
    data = r.json()
    assert "key" in data
    assert "." in data["key"]  # key_id.raw_material format


async def test_revoke_api_key_then_use(auth_client: AsyncClient) -> None:
    login = await auth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-password"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create key.
    create_r = await auth_client.post(
        "/auth/api-keys", json={"name": "temp-key"}, headers=headers
    )
    key_id = create_r.json()["id"]
    full_key = create_r.json()["key"]

    # Key works before revocation.
    me_r = await auth_client.get("/auth/me", headers={"X-Api-Key": full_key})
    assert me_r.status_code == 200

    # Revoke.
    del_r = await auth_client.delete(f"/auth/api-keys/{key_id}", headers=headers)
    assert del_r.status_code == 204

    # Key no longer works.
    me_r2 = await auth_client.get("/auth/me", headers={"X-Api-Key": full_key})
    assert me_r2.status_code == 401


async def test_refresh_token(auth_client: AsyncClient) -> None:
    login = await auth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-password"},
    )
    refresh_token = login.json()["refresh_token"]

    r = await auth_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert r.status_code == 200
    assert "access_token" in r.json()
