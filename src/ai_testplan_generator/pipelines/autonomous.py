"""AutonomousPipeline - the 'fire-and-forget' entrypoint.

Typical usage:

    brain = Brain.build()
    pipeline = AutonomousPipeline(brain)

    # Ingest docs for a project (extracts requirements).
    await brain.project_kb("proj-42").ingest_many([p1, p2, p3])

    # Let the supervised agent graph produce a reviewed, scheduled plan.
    result = await pipeline.run(
        project_id="proj-42",
        goal="Qualify the pump controller against SRS v3 and ISO 4413.",
        detail_level=DetailLevel.DETAILED,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import structlog

from ai_testplan_generator.agents import AutonomousState
from ai_testplan_generator.graphs import build_autonomous_graph
from ai_testplan_generator.models import DetailLevel, TestPlan, TestSchedule
from ai_testplan_generator.pipelines.brain import Brain

_log = structlog.get_logger(__name__)


@dataclass
class AutonomousResult:
    session_id: str
    plan: TestPlan | None
    schedule: TestSchedule | None
    state: AutonomousState


class AutonomousPipeline:
    def __init__(self, brain: Brain) -> None:
        self._brain = brain

    async def run(
        self,
        *,
        project_id: str,
        goal: str,
        detail_level: DetailLevel = DetailLevel.DETAILED,
        max_revision_rounds: int = 3,
        session_id: str | None = None,
    ) -> AutonomousResult:
        session_id = session_id or f"sess_{uuid4().hex[:10]}"
        ctx = self._brain.context(session_id=session_id, project_id=project_id)
        graph = build_autonomous_graph(ctx)

        # Load already-registered docs / requirements for this project
        # (ingestion commits them to memory; we just mirror them onto state
        # so the graph can reason over counts without touching memory each
        # time).
        docs = await self._brain.memory.get_documents_for_project(project_id)
        reqs = await self._brain.memory.get_requirements_for_project(project_id)

        initial = AutonomousState(
            session_id=session_id,
            project_id=project_id,
            goal=goal,
            detail_level=detail_level,
            documents=docs,
            requirements=reqs,
            max_revision_rounds=max_revision_rounds,
        )
        _log.info("autonomous_start", session_id=session_id, goal=goal)
        final: AutonomousState = await graph.ainvoke(initial)
        # LangGraph may return a dict-like; coerce to our typed state.
        state = (
            final if isinstance(final, AutonomousState) else AutonomousState.model_validate(final)
        )
        _log.info(
            "autonomous_done",
            session_id=session_id,
            n_tests=len(state.test_cases),
            scheduled=state.schedule is not None,
        )
        return AutonomousResult(
            session_id=session_id, plan=state.plan, schedule=state.schedule, state=state
        )
