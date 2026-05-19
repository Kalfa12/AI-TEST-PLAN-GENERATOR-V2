"""Autonomous LangGraph.

Topology (supervisor pattern):

                        +--> analyst
                        +--> extractor
                        +--> architect
    START -> orchestrator --> generator
                        +--> traceability
                        +--> reviewer -------> orchestrator (loop)
                        +--> planner
                        +--> END

Every worker returns to the orchestrator, which re-examines state and
routes again. The orchestrator itself has a revision budget so we can
never loop forever on review -> generator.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ai_testplan_generator.agents import (
    AutonomousState,
    CorpusSummary,
    DocumentAnalystAgent,
    OrchestratorAgent,
    PlannerAgent,
    RequirementExtractorAgent,
    RequirementReviewerAgent,
    ReviewerAgent,
    TestArchitectAgent,
    TestGeneratorAgent,
    TraceabilityAgent,
    build_defect_report,
)
from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.models import Chunk


def build_autonomous_graph(ctx: AgentContext) -> Any:
    """Compile the autonomous multi-agent graph.

    The returned object is a `CompiledGraph`; call `.ainvoke(state)` on
    it to run end-to-end. A checkpointer can be attached at compile time
    by the caller if they want time-travel / resumability.
    """

    orchestrator = OrchestratorAgent(ctx)
    analyst = DocumentAnalystAgent(ctx)
    extractor = RequirementExtractorAgent(ctx)
    requirement_reviewer = RequirementReviewerAgent(ctx)
    architect = TestArchitectAgent(ctx)
    generator = TestGeneratorAgent(ctx)
    traceability = TraceabilityAgent(ctx)
    reviewer = ReviewerAgent(ctx)
    planner = PlannerAgent(ctx)

    graph: StateGraph = StateGraph(AutonomousState)

    # --- nodes ---------------------------------------------------------------

    async def _orchestrate(state: AutonomousState) -> dict[str, Any]:
        decision = await orchestrator.invoke(state)
        return {"last_route": decision.route_to, "finished": decision.route_to == "finish"}

    async def _analyst(state: AutonomousState) -> dict[str, Any]:
        await analyst.invoke(DocumentAnalystAgent.Input(documents=state.documents))
        return {}

    async def _extractor(state: AutonomousState) -> dict[str, Any]:
        project_chunks: list[Chunk] = []
        for doc in state.documents:
            project_chunks.extend(await ctx.memory.get_chunks_for_document(doc.id))
        out = await extractor.invoke(
            RequirementExtractorAgent.Input(chunks=project_chunks)
        )
        return {"requirements": out.requirements}

    async def _requirement_reviewer(state: AutonomousState) -> dict[str, Any]:
        report = await requirement_reviewer.invoke(
            RequirementReviewerAgent.Input(requirements=state.requirements)
        )
        return {"requirement_review_report": report}

    async def _architect(state: AutonomousState) -> dict[str, Any]:
        plan = await architect.invoke(
            TestArchitectAgent.Input(
                goal=state.goal,
                detail_level=state.detail_level,
                requirements=state.requirements,
            )
        )
        return {"plan": plan}

    async def _generator(state: AutonomousState) -> dict[str, Any]:
        if state.plan is None:
            return {"error": "generator called without a plan"}
        out = await generator.invoke(
            TestGeneratorAgent.Input(
                requirements=state.requirements, detail_level=state.detail_level
            )
        )
        if not out.test_cases:
            return {"error": "generator failed to produce any valid test cases (all LLM calls failed or timed out)"}
        state.plan.test_cases = out.test_cases
        # Always clear stale traceability/review/defect state so the orchestrator
        # is forced back through traceability → reviewer → defect_aggregator on
        # the next pass. Without this, revision_round never increments and the
        # loop is infinite.
        return {
            "plan": state.plan,
            "test_cases": out.test_cases,
            "trace_report": None,
            "review_report": None,
            "defect_report": None,
        }

    async def _traceability(state: AutonomousState) -> dict[str, Any]:
        if state.plan is None:
            return {"error": "traceability called without a plan"}
        report = await traceability.invoke(
            TraceabilityAgent.Input(plan=state.plan, requirements=state.requirements)
        )
        return {"trace_report": report, "plan": state.plan}

    async def _reviewer(state: AutonomousState) -> dict[str, Any]:
        if state.plan is None:
            return {"error": "reviewer called without a plan"}
        report = await reviewer.invoke(ReviewerAgent.Input(plan=state.plan))
        updates: dict[str, Any] = {
            "review_report": report,
            "revision_round": state.revision_round + 1,
        }
        return updates

    async def _planner(state: AutonomousState) -> dict[str, Any]:
        if state.plan is None:
            return {"error": "planner called without a plan"}
        schedule = await planner.invoke(PlannerAgent.Input(plan=state.plan, resources=[]))
        return {"schedule": schedule}

    async def _defect_aggregator(state: AutonomousState) -> dict[str, Any]:
        report = build_defect_report(
            plan=state.plan,
            requirements=state.requirements,
            review_report=state.review_report,
            requirement_review_report=state.requirement_review_report,
            trace_report=state.trace_report,
        )
        return {"defect_report": report}

    # --- wiring --------------------------------------------------------------

    graph.add_node("orchestrator", _orchestrate)
    graph.add_node("analyst", _analyst)
    graph.add_node("extractor", _extractor)
    graph.add_node("requirement_reviewer", _requirement_reviewer)
    graph.add_node("architect", _architect)
    graph.add_node("generator", _generator)
    graph.add_node("traceability", _traceability)
    graph.add_node("reviewer", _reviewer)
    graph.add_node("defect_aggregator", _defect_aggregator)
    graph.add_node("planner", _planner)

    graph.set_entry_point("orchestrator")

    def _route(state: AutonomousState) -> str:
        if state.finished or state.error:
            return END
        return state.last_route or "analyst"

    graph.add_conditional_edges(
        "orchestrator",
        _route,
        {
            "analyst": "analyst",
            "extractor": "extractor",
            "requirement_reviewer": "requirement_reviewer",
            "architect": "architect",
            "generator": "generator",
            "traceability": "traceability",
            "reviewer": "reviewer",
            "defect_aggregator": "defect_aggregator",
            "planner": "planner",
            END: END,
        },
    )

    # Every worker returns to the orchestrator.
    for worker in (
        "analyst",
        "extractor",
        "requirement_reviewer",
        "architect",
        "generator",
        "traceability",
        "reviewer",
        "defect_aggregator",
        "planner",
    ):
        graph.add_edge(worker, "orchestrator")

    return graph.compile()


# Re-export for type-checkers that look at symbols.
__all__ = ["build_autonomous_graph", "CorpusSummary"]
