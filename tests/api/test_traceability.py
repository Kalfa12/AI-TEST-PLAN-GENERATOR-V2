"""M09: Traceability endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestTraceability:
    async def test_trace_artefact_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/trace/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    async def test_trace_ancestors_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/trace/nonexistent/ancestors")
        assert resp.status_code == 404

    async def test_project_coverage_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-empty/coverage")
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_project_gaps_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-empty/gaps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["uncovered_requirement_ids"] == []
