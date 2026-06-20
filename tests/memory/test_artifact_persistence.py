"""Durable artefact integration tests for MemoryManager."""

from __future__ import annotations

from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.memory.manager import MemoryManager
from ai_testplan_generator.models import (
    DetailLevel,
    Resource,
    TestCaseStatus as CaseStatus,
    TestPlan as PlanModel,
    TestSchedule as Schedule,
)
from ai_testplan_generator.models.planning import ScheduledAssignment
from conftest import (
    MockLLMGateway,
    make_chunk,
    make_document,
    make_requirement,
    make_section,
    make_test_case,
)


async def test_memory_manager_reads_artefacts_written_by_another_instance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = str(tmp_path / "artifacts.db")
    writer_repo = await ArtifactRepository.create(db_path=db_path)
    reader_repo = await ArtifactRepository.create(db_path=db_path)

    writer = MemoryManager(llm=MockLLMGateway(), artifact_repo=writer_repo)
    reader = MemoryManager(llm=MockLLMGateway(), artifact_repo=reader_repo)

    doc = make_document(project_id="proj-cross-process", title="Worker Spec")
    section = make_section(doc.id)
    chunk = make_chunk(doc.id, section.id)
    req = make_requirement(
        project_id="proj-cross-process",
        source_document_id=doc.id,
        source_chunk_ids=[chunk.id],
    )
    tc = make_test_case(requirement_ids=[req.id])
    plan = PlanModel(
        project_id="proj-cross-process",
        title="Worker Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Qualification",
        strategy="Cover every requirement.",
        test_cases=[tc],
        coverage_matrix={req.id: [tc.id]},
    )

    await writer.register_document(doc)
    await writer.register_sections([section])
    await writer.register_chunks([chunk])
    await writer.register_requirements([req])
    await writer.register_test_plan(plan)

    assert [d.id for d in await reader.get_documents_for_project("proj-cross-process")] == [doc.id]
    assert [r.id for r in await reader.get_requirements_for_project("proj-cross-process")] == [req.id]
    assert [c.id for c in await reader.get_chunks_by_ids([chunk.id])] == [chunk.id]

    plans = await reader.get_test_plans_for_project("proj-cross-process")
    assert [p.id for p in plans] == [plan.id]
    assert plans[0].test_cases[0].id == tc.id
    assert reader.graph.coverage_matrix([req.id]) == {req.id: [tc.id]}

    await writer_repo.close()
    await reader_repo.close()


async def test_memory_manager_hydrates_graph_from_durable_store(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = str(tmp_path / "artifacts.db")
    repo = await ArtifactRepository.create(db_path=db_path)
    writer = MemoryManager(llm=MockLLMGateway(), artifact_repo=repo)

    doc = make_document(project_id="proj-hydrate")
    section = make_section(doc.id)
    chunk = make_chunk(doc.id, section.id)
    req = make_requirement(
        project_id="proj-hydrate",
        source_document_id=doc.id,
        source_chunk_ids=[chunk.id],
    )
    tc = make_test_case(requirement_ids=[req.id])
    plan = PlanModel(
        project_id="proj-hydrate",
        title="Hydrated Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Qualification",
        strategy="Cover every requirement.",
        test_cases=[tc],
        coverage_matrix={req.id: [tc.id]},
    )
    await writer.register_document(doc)
    await writer.register_sections([section])
    await writer.register_chunks([chunk])
    await writer.register_requirements([req])
    await writer.register_test_plan(plan)
    await repo.close()

    reopened = await ArtifactRepository.create(db_path=db_path)
    hydrated = MemoryManager(llm=MockLLMGateway(), artifact_repo=reopened)
    await hydrated.hydrate()

    assert [d.id for d in await hydrated.get_documents_for_project("proj-hydrate")] == [doc.id]
    assert hydrated.graph.coverage_matrix([req.id]) == {req.id: [tc.id]}
    req_ancestors = hydrated.graph.ancestors(req.id, depth=3)
    assert chunk.id in req_ancestors
    assert doc.id in req_ancestors

    await reopened.close()


async def test_resources_and_schedule_survive_repository_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = str(tmp_path / "planning.db")
    repo = await ArtifactRepository.create(db_path=db_path)

    resource = Resource(
        id="res_bench",
        project_id="proj-planning",
        name="Validation bench",
        service="System test lab",
        role="Technician",
    )
    tc = make_test_case()
    tc.id = "tc_sched"
    tc.status = CaseStatus.PLANNED
    tc.assignee = resource.name
    plan = PlanModel(
        id="plan_sched",
        project_id="proj-planning",
        title="Scheduled Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Qualification",
        strategy="Resource-backed execution.",
        test_cases=[tc],
        schedule=Schedule(
            plan_id="plan_sched",
            assignments={
                tc.id: ScheduledAssignment(
                    start="2099-01-02",
                    end="2099-01-03",
                    resource_ids=[resource.id],
                    service=resource.service,
                )
            },
        ),
    )

    await repo.save_resource(resource)
    await repo.save_test_plan(plan)
    await repo.close()

    reopened = await ArtifactRepository.create(db_path=db_path)
    resources = await reopened.list_resources("proj-planning")
    reloaded_plan = await reopened.get_test_plan("plan_sched")

    assert [r.id for r in resources] == [resource.id]
    assert reloaded_plan is not None
    assert reloaded_plan.schedule is not None
    assert reloaded_plan.schedule.assignments[tc.id].resource_ids == [resource.id]
    assert reloaded_plan.test_cases[0].status == CaseStatus.PLANNED
    assert reloaded_plan.test_cases[0].assignee == resource.name

    await reopened.close()


async def test_test_case_status_update_is_persisted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = str(tmp_path / "status.db")
    repo = await ArtifactRepository.create(db_path=db_path)
    tc = make_test_case()
    plan = PlanModel(
        project_id="proj-status",
        title="Status Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Qualification",
        strategy="Track execution.",
        test_cases=[tc],
    )
    await repo.save_test_plan(plan)

    updated = await repo.update_test_case_status(
        project_id="proj-status",
        plan_id=plan.id,
        test_case_id=tc.id,
        status=CaseStatus.BLOCKED,
        status_note="Waiting for bench availability.",
    )
    assert updated is not None
    await repo.close()

    reopened = await ArtifactRepository.create(db_path=db_path)
    reloaded = await reopened.get_test_plan(plan.id)
    assert reloaded is not None
    assert reloaded.test_cases[0].status == CaseStatus.BLOCKED
    assert reloaded.test_cases[0].status_note == "Waiting for bench availability."

    await reopened.close()
