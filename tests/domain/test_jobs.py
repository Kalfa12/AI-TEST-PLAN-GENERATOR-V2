from __future__ import annotations

from ai_testplan_generator.agents.state import AutonomousState
from ai_testplan_generator.api.jobs import Job
from ai_testplan_generator.domain.jobs import JobRepository
from ai_testplan_generator.models import DetailLevel
from tests.conftest import make_requirement


async def test_job_repository_persists_checkpoint_across_reopen(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = str(tmp_path / "jobs.db")
    repo = await JobRepository.create(db_path=db_path)
    job = Job(
        id="job_checkpoint",
        kind="run_autonomous_interactive",
        session_id="sess_checkpoint",
    )
    state = AutonomousState(
        session_id="sess_checkpoint",
        project_id="project-a",
        goal="Generate a restart-safe test plan",
        detail_level=DetailLevel.DETAILED,
        requirements=[make_requirement(project_id="project-a")],
        interactive=True,
    )
    job.pause(agent="extractor", state=state)

    await repo.save_checkpoint(
        job=job,
        paused_at="extractor",
        state=state.model_dump(mode="json"),
        project_id="project-a",
    )
    await repo.close()

    reopened = await JobRepository.create(db_path=db_path)
    stored_job = await reopened.get_job("job_checkpoint")
    checkpoint = await reopened.get_checkpoint("job_checkpoint")

    assert stored_job is not None
    assert stored_job.status.value == "paused"
    assert stored_job.paused_at == "extractor"
    assert stored_job.session_id == "sess_checkpoint"
    assert checkpoint is not None
    assert checkpoint.job_id == "job_checkpoint"
    assert checkpoint.paused_at == "extractor"
    assert checkpoint.state["goal"] == "Generate a restart-safe test plan"
    assert checkpoint.state["requirements"][0]["project_id"] == "project-a"

    await reopened.close()
