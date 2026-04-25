"""M07: Test plan generation endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestPlanCreation:
    async def test_create_plan_returns_202(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/projects/proj-1/plans",
            json={"goal": "Test the pump controller.", "detail_level": "detailed"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert "session_id" in body
        assert body["session_id"].startswith("sess_")

    async def test_create_plan_invalid_rounds(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/projects/proj-1/plans",
            json={"goal": "Test.", "max_revision_rounds": 99},
        )
        assert resp.status_code == 422

    async def test_list_plans_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-empty/plans")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []

    async def test_get_plan_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj-1/plans/plan_nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    async def test_delete_plan_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/projects/proj-1/plans/plan_nonexistent")
        assert resp.status_code == 404


class TestJobStatus:
    async def test_get_job_after_create(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects/proj-1/plans",
            json={"goal": "Test something."},
        )
        job_id = create_resp.json()["job_id"]
        job_resp = await client.get(f"/jobs/{job_id}")
        assert job_resp.status_code == 200
        body = job_resp.json()
        assert body["id"] == job_id
        assert body["status"] in ("queued", "in_progress", "succeeded", "failed")

    async def test_get_job_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/jobs/job_nonexistent")
        assert resp.status_code == 404
