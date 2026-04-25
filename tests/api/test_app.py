"""M05: FastAPI skeleton — liveness, readiness, error handling."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


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


class TestOpenAPI:
    async def test_openapi_schema_reachable(self, client: AsyncClient) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/healthz" in schema["paths"]
