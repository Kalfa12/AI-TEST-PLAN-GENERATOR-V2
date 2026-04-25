"""M17: Job queue and status endpoints.

Redis-dependent integration tests are skipped unless REDIS_URL is set.
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

_redis_available = bool(os.getenv("REDIS_URL"))


class TestJobStatusEndpoint:
    async def test_get_job_after_plan_creation(self, client: AsyncClient) -> None:
        """POST /plans returns a job_id; GET /jobs/{job_id} returns 200."""
        create_resp = await client.post(
            "/projects/proj-1/plans",
            json={"goal": "Verify the hydraulic system.", "detail_level": "detailed"},
        )
        assert create_resp.status_code == 202
        body = create_resp.json()
        assert "job_id" in body
        job_id = body["job_id"]

        job_resp = await client.get(f"/jobs/{job_id}")
        assert job_resp.status_code == 200
        data = job_resp.json()
        assert data["id"] == job_id
        assert data["status"] in ("queued", "in_progress", "succeeded", "failed")

    async def test_get_job_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/jobs/job_does_not_exist_xyz")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    async def test_document_upload_large_returns_job_id(
        self,
        client: AsyncClient,
        api_settings,
    ) -> None:
        """Uploading a file larger than the threshold returns a job_id in the body."""
        threshold = api_settings.large_doc_threshold_bytes
        content = b"x" * (threshold + 1)
        resp = await client.post(
            "/projects/proj-1/documents",
            files={"file": ("large.txt", content, "text/plain")},
        )
        # Documents route uses status_code=200 for both sync and accepted responses.
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["job_id"]  # non-empty string

    async def test_job_kind_matches_task(self, client: AsyncClient) -> None:
        """The job returned by GET /jobs/{id} has the correct kind."""
        create_resp = await client.post(
            "/projects/proj-1/plans",
            json={"goal": "Check the motor controller."},
        )
        job_id = create_resp.json()["job_id"]
        job_resp = await client.get(f"/jobs/{job_id}")
        data = job_resp.json()
        assert data["kind"] == "run_autonomous"


@pytest.mark.skipif(
    not _redis_available,
    reason="REDIS_URL not set — skipping real ARQ integration tests",
)
class TestARQIntegration:
    async def test_real_enqueue_and_poll(self, client: AsyncClient) -> None:
        """Full ARQ round-trip: enqueue → poll until succeeded/failed."""
        import asyncio

        create_resp = await client.post(
            "/projects/proj-redis/plans",
            json={"goal": "Integration test plan."},
        )
        assert create_resp.status_code == 202
        job_id = create_resp.json()["job_id"]

        for _ in range(20):
            await asyncio.sleep(1)
            resp = await client.get(f"/jobs/{job_id}")
            assert resp.status_code == 200
            status = resp.json()["status"]
            if status in ("succeeded", "failed"):
                break
        assert status in ("succeeded", "failed"), f"Job still pending after timeout: {status}"
