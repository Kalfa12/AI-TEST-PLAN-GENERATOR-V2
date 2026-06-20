from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai_testplan_generator.agents.state import AutonomousState
from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api.deps import (
    get_current_user,
    get_job_repo,
    get_job_queue,
    get_project_repo,
)
from ai_testplan_generator.api.errors import NotFoundError
from ai_testplan_generator.api.jobs import Job
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.jobs import JobRepository
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.models import DetailLevel
from tests.conftest import make_requirement


class RepoOnlyQueue:
    def __init__(self, repo: JobRepository) -> None:
        self._repo = repo

    async def enqueue(self, task_name: str, **kwargs: Any) -> str:
        raise RuntimeError("not used")

    async def get_status(self, job_id: str) -> Job:
        job = await self._repo.get_job(job_id)
        if job is None:
            raise NotFoundError(f"Job '{job_id}' not found.")
        return job

    async def get_dead_letter_entries(self) -> list[Any]:
        return []

    async def requeue_dead_letter(self, job_id: str) -> str:
        raise NotFoundError(f"Dead-letter job '{job_id}' not found.")


@pytest.fixture
def checkpoint_state() -> AutonomousState:
    return AutonomousState(
        session_id="sess_api_checkpoint",
        project_id="project-a",
        goal="Generate checkpointed plan",
        detail_level=DetailLevel.DETAILED,
        requirements=[make_requirement(project_id="project-a")],
        interactive=True,
    )


async def test_checkpoint_endpoint_reads_durable_state_without_live_job(
    tmp_path,
    checkpoint_state: AutonomousState,
) -> None:
    settings = Settings(APP_DB_PATH=str(tmp_path / "app.db"), API_DEBUG=True)
    repo = await JobRepository.create(db_path=settings.app_db_path)
    project_repo = await ProjectRepository.create(db_path=settings.app_db_path)
    job = Job(
        id="job_api_checkpoint",
        kind="run_autonomous_interactive",
        session_id=checkpoint_state.session_id,
    )
    job.pause(agent="architect", state=checkpoint_state)
    await repo.save_checkpoint(
        job=job,
        paused_at="architect",
        state=checkpoint_state.model_dump(mode="json"),
        project_id="project-a",
    )

    app = create_app(settings=settings)
    app.dependency_overrides[get_job_repo] = lambda: repo
    app.dependency_overrides[get_job_queue] = lambda: RepoOnlyQueue(repo)
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_current_user] = lambda: User(
        id="usr_checkpoint",
        email="checkpoint@test.local",
        display_name="Checkpoint Tester",
        is_admin=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get("/jobs/job_api_checkpoint/checkpoint")

    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job_api_checkpoint"
    assert body["paused_at"] == "architect"
    assert body["state"]["goal"] == "Generate checkpointed plan"
    assert body["state"]["requirements"][0]["project_id"] == "project-a"

    await repo.close()
    await project_repo.close()


async def test_resume_endpoint_stores_durable_directive_without_live_signal(
    tmp_path,
    checkpoint_state: AutonomousState,
) -> None:
    settings = Settings(APP_DB_PATH=str(tmp_path / "app.db"), API_DEBUG=True)
    repo = await JobRepository.create(db_path=settings.app_db_path)
    project_repo = await ProjectRepository.create(db_path=settings.app_db_path)
    job = Job(
        id="job_api_resume",
        kind="run_autonomous_interactive",
        session_id=checkpoint_state.session_id,
    )
    job.pause(agent="extractor", state=checkpoint_state)
    await repo.save_checkpoint(
        job=job,
        paused_at="extractor",
        state=checkpoint_state.model_dump(mode="json"),
        project_id="project-a",
    )

    app = create_app(settings=settings)
    app.dependency_overrides[get_job_repo] = lambda: repo
    app.dependency_overrides[get_job_queue] = lambda: RepoOnlyQueue(repo)
    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_current_user] = lambda: User(
        id="usr_resume",
        email="resume@test.local",
        display_name="Resume Tester",
        is_admin=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/jobs/job_api_resume/resume",
            json={"action": "reprompt", "feedback": "Focus on safety requirements."},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "job_api_resume"
    assert body["status"] == "paused"
    checkpoint = await repo.get_checkpoint("job_api_resume")
    assert checkpoint is not None
    assert checkpoint.directive == {
        "action": "reprompt",
        "feedback": "Focus on safety requirements.",
    }

    await repo.close()
    await project_repo.close()
