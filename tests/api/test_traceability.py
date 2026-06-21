"""M09: Traceability endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from ai_testplan_generator.api.deps import get_brain
from tests.conftest import make_requirement


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

    async def test_project_requirements_lists_extracted_requirements(
        self,
        client: AsyncClient,
    ) -> None:
        app = client._transport.app  # type: ignore[attr-defined]
        brain = app.dependency_overrides[get_brain]()
        req = make_requirement(
            project_id="proj-reqs",
            statement="The controller shall reject invalid firmware signatures.",
        )
        await brain.memory.register_requirements([req])

        resp = await client.get("/projects/proj-reqs/requirements")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == req.id
        assert body["items"][0]["statement"] == req.statement
