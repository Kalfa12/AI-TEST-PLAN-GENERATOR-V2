"""M05: FastAPI skeleton — liveness, readiness, error handling."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.config import DEFAULT_JWT_SECRET, Settings


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
