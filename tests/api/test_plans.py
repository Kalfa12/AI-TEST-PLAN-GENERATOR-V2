"""M07: Test plan generation endpoints."""

from __future__ import annotations

from httpx import AsyncClient

from ai_testplan_generator.api.deps import get_brain, get_job_queue
from ai_testplan_generator.api.jobs import Job
from tests.conftest import make_requirement


class SpyQueue:
    def __init__(self) -> None:
        self.last_task_name: str | None = None
        self.last_kwargs: dict[str, object] | None = None

    async def enqueue(self, task_name: str, **kwargs: object) -> str:
        self.last_task_name = task_name
        self.last_kwargs = kwargs
        return "job_spy"

    async def get_status(self, job_id: str) -> Job:
        return Job(id=job_id, kind=self.last_task_name or "")

    async def get_dead_letter_entries(self) -> list[object]:
        return []

    async def requeue_dead_letter(self, job_id: str) -> str:
        return job_id


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

    async def test_create_plan_selected_requires_ids(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.post(
            "/projects/proj-1/plans",
            json={
                "goal": "Test selected requirements.",
                "requirement_mode": "selected",
            },
        )

        assert resp.status_code == 422

    async def test_create_plan_rejects_ids_outside_project(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.post(
            "/projects/proj-1/plans",
            json={
                "goal": "Test selected requirements.",
                "requirement_mode": "selected",
                "requirement_ids": ["req_missing"],
            },
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"

    async def test_create_plan_enqueues_requirement_scope(
        self,
        client: AsyncClient,
    ) -> None:
        app = client._transport.app  # type: ignore[attr-defined]
        brain = app.dependency_overrides[get_brain]()
        req = make_requirement(project_id="proj-scope")
        await brain.memory.register_requirements([req])
        queue = SpyQueue()
        app.dependency_overrides[get_job_queue] = lambda: queue

        resp = await client.post(
            "/projects/proj-scope/plans",
            json={
                "goal": "Test selected requirements.",
                "detail_level": "detailed",
                "requirement_mode": "selected",
                "requirement_ids": [req.id],
                "interactive": True,
            },
        )

        assert resp.status_code == 202
        assert queue.last_task_name == "run_autonomous_interactive"
        assert queue.last_kwargs is not None
        assert queue.last_kwargs["requirement_mode"] == "selected"
        assert queue.last_kwargs["requirement_ids"] == [req.id]

    async def test_create_plan_uses_default_goal_when_blank(
        self,
        client: AsyncClient,
    ) -> None:
        app = client._transport.app  # type: ignore[attr-defined]
        queue = SpyQueue()
        app.dependency_overrides[get_job_queue] = lambda: queue

        resp = await client.post(
            "/projects/proj-default-goal/plans",
            json={"goal": "   ", "detail_level": "detailed"},
        )

        assert resp.status_code == 202
        assert queue.last_kwargs is not None
        assert (
            queue.last_kwargs["goal"]
            == "Generate a complete test plan from the current project requirements."
        )

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
