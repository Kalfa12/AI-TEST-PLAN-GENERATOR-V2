"""M05: FastAPI skeleton — liveness, readiness, error handling."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.config import DEFAULT_JWT_SECRET, Settings
from ai_testplan_generator.storage.local_fs import LocalFilesystemBlobStore


class FailingBlobStore(LocalFilesystemBlobStore):
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        raise RuntimeError("blob store unavailable")


class TestLiveness:
    async def test_healthz_returns_200(self, client: AsyncClient) -> None:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_readyz_returns_200_with_inmemory_backends(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/readyz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "checks" in body
        assert body["checks"]["api"] == "ok"
        assert body["checks"]["project_db"] == "ok"
        assert body["checks"]["blob_store"] == "ok"
        assert body["checks"]["redis"] == "not_configured"

    async def test_readyz_returns_503_when_blob_store_fails(
        self, client: AsyncClient, tmp_path
    ) -> None:  # type: ignore[no-untyped-def]
        from ai_testplan_generator.api.deps import get_blob_store

        failing = FailingBlobStore(root=str(tmp_path / "bad-blobs"))
        client._transport.app.dependency_overrides[get_blob_store] = lambda: failing  # type: ignore[attr-defined]

        resp = await client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["blob_store"] == "unavailable"
        assert "blob_store" in body["unhealthy"]

    async def test_readyz_checks_redis_when_event_broker_uses_redis(
        self, client: AsyncClient
    ) -> None:
        from ai_testplan_generator.api.deps import get_settings

        redis_settings = Settings(
            SEMANTIC_MEMORY_BACKEND="inmemory",
            EPISODIC_MEMORY_BACKEND="inmemory",
            CROSSDOC_GRAPH_BACKEND="networkx",
            EVENT_BROKER_BACKEND="redis",
            REDIS_URL="redis://127.0.0.1:1/0",
            API_DEBUG=True,
        )
        client._transport.app.dependency_overrides[get_settings] = lambda: redis_settings  # type: ignore[attr-defined]

        resp = await client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["checks"]["redis"] == "unavailable"
        assert "redis" in body["unhealthy"]

    async def test_unknown_path_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/no-such-path")
        assert resp.status_code == 404


class TestCORS:
    async def test_cors_headers_present(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/healthz",
            headers={"Origin": "http://example.com",
                     "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" in resp.headers

    def test_production_rejects_wildcard_cors(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        settings = Settings(
            API_DEBUG=False,
            API_CORS_ORIGINS=["*"],
            JWT_SECRET="secure-test-secret-for-production-checks",
            APP_DB_PATH=str(tmp_path / "app.db"),
        )
        with pytest.raises(ValueError, match="API_CORS_ORIGINS"):
            create_app(settings=settings)

    def test_production_rejects_default_jwt_secret(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        settings = Settings(
            API_DEBUG=False,
            API_CORS_ORIGINS=["https://app.example.com"],
            JWT_SECRET=DEFAULT_JWT_SECRET,
            JWT_PRIVATE_KEY_PATH=None,
            APP_DB_PATH=str(tmp_path / "app.db"),
        )
        with pytest.raises(ValueError, match="JWT_SECRET"):
            create_app(settings=settings)


class TestOpenAPI:
    async def test_openapi_schema_reachable(self, client: AsyncClient) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/healthz" in schema["paths"]
