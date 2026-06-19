"""Tests for the durable artefact repository."""

from __future__ import annotations

from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.models import DetailLevel, TestPlan as PlanModel
from conftest import make_chunk, make_document, make_requirement, make_section, make_test_case


async def test_artifact_repository_round_trips_core_artefacts(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    repo = await ArtifactRepository.create(db_path=str(tmp_path / "artifacts.db"))

    doc = make_document(project_id="proj-durable", title="Durable Spec")
    section = make_section(doc.id)
    chunk = make_chunk(doc.id, section.id)
    req = make_requirement(
        project_id="proj-durable",
        source_document_id=doc.id,
        source_chunk_ids=[chunk.id],
    )
    tc = make_test_case(requirement_ids=[req.id])
    plan = PlanModel(
        project_id="proj-durable",
        title="Durable Plan",
        detail_level=DetailLevel.DETAILED,
        scope="Qualification",
        strategy="Trace every requirement to a test.",
        test_cases=[tc],
        coverage_matrix={req.id: [tc.id]},
    )

    await repo.save_document(doc)
    await repo.save_sections([section])
    await repo.save_chunks([chunk])
    await repo.save_requirements([req])
    await repo.save_test_plan(plan)
    await repo.close()

    reopened = await ArtifactRepository.create(db_path=str(tmp_path / "artifacts.db"))
    assert [d.id for d in await reopened.list_documents("proj-durable")] == [doc.id]
    assert [c.id for c in await reopened.list_chunks_for_document(doc.id)] == [chunk.id]
    assert [r.id for r in await reopened.list_requirements("proj-durable")] == [req.id]

    restored_plan = await reopened.get_test_plan(plan.id)
    assert restored_plan is not None
    assert restored_plan.id == plan.id
    assert restored_plan.test_cases[0].id == tc.id
    assert restored_plan.coverage_matrix == {req.id: [tc.id]}
    await reopened.close()
