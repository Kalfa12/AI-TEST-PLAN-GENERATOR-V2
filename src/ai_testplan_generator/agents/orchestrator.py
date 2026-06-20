"""OrchestratorAgent - the supervisor.

Given the current autonomous state, decides which agent runs next. This
agent does not itself touch documents or tests - it's a router.

The decision is a structured enum so the LangGraph conditional edge can
dispatch deterministically. The LLM is only used for the "tricky" calls
(e.g. whether the reviewer's findings warrant another revision). Fast
path decisions (no requirements yet -> extractor; no plan yet -> architect)
are taken procedurally without burning a round-trip.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.agents.state import AutonomousState
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.prompts.library import ORCHESTRATOR_SYSTEM, with_industry_context

NextStep = Literal[
    "analyst",
    "extractor",
    "requirement_reviewer",
    "architect",
    "generator",
    "traceability",
    "reviewer",
    "defect_aggregator",
    "planner",
    "finish",
]


class OrchestratorDecision(BaseModel):
    route_to: NextStep
    rationale: str


class OrchestratorAgent(BaseAgent[AutonomousState, OrchestratorDecision]):
    name = "orchestrator"
    Input = AutonomousState

    async def run(self, inp: AutonomousState) -> OrchestratorDecision:
        # --- procedural fast paths ---------------------------------------
        if inp.error:
            return OrchestratorDecision(route_to="finish", rationale=f"error={inp.error}")

        if not inp.documents:
            return OrchestratorDecision(
                route_to="finish", rationale="no documents ingested; nothing to do"
            )

        if not self.ctx.memory.working.get(self.ctx.session_id, "corpus_summary"):
            return OrchestratorDecision(
                route_to="analyst", rationale="corpus not yet summarised"
            )

        if not inp.requirements:
            return OrchestratorDecision(
                route_to="extractor", rationale="no requirements extracted yet"
            )

        if inp.requirement_review_report is None:
            return OrchestratorDecision(
                route_to="requirement_reviewer",
                rationale="requirements not yet reviewed for taxonomy defects",
            )

        if inp.plan is None or not inp.plan.scope:
            return OrchestratorDecision(
                route_to="architect", rationale="no plan shell yet"
            )

        if not inp.test_cases:
            return OrchestratorDecision(
                route_to="generator", rationale="plan shell has no test cases"
            )

        if inp.trace_report is None:
            return OrchestratorDecision(
                route_to="traceability", rationale="traceability not yet validated"
            )

        if inp.review_report is None:
            return OrchestratorDecision(
                route_to="reviewer", rationale="first review pending"
            )

        if inp.defect_report is None:
            return OrchestratorDecision(
                route_to="defect_aggregator",
                rationale="defect report not yet aggregated",
            )

        # --- LLM-assisted branch: revise or schedule? --------------------
        rr = inp.review_report
        has_critical = any(f.severity == "critical" for f in rr.findings)
        has_major = any(f.severity == "major" for f in rr.findings)
        defect_critical = inp.defect_report.summary.get("critical", 0) > 0
        budget_left = inp.revision_round < inp.max_revision_rounds

        if (has_critical or has_major or defect_critical) and budget_left:
            # Ask the LLM whether it truly justifies a loopback or whether
            # findings are actionable in-place.
            industry = await self.ctx.project_industry()
            messages = [
                ChatMessage(
                    role="system",
                    content=with_industry_context(ORCHESTRATOR_SYSTEM, industry),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"revision_round={inp.revision_round}/{inp.max_revision_rounds}\n"
                        f"approved={rr.approved}\n"
                        f"findings={[f.model_dump() for f in rr.findings]}\n"
                        "Decide: generator (revise test cases) / planner (move on) / finish."
                    ),
                ),
            ]
            decision = await self.ctx.llm.complete_structured(
                messages, OrchestratorDecision, role="fast", temperature=0.0
            )
            # Clamp: at this stage the only valid loopback is "generator";
            # any other route (analyst, extractor, etc.) would be nonsense and
            # would cause the pipeline to re-run expensive early stages.
            if decision.route_to not in ("generator", "planner", "finish"):
                decision = OrchestratorDecision(
                    route_to="planner",
                    rationale=f"clamped from invalid route '{decision.route_to}'",
                )
            return decision

        if inp.schedule is None:
            return OrchestratorDecision(
                route_to="planner", rationale="plan reviewed and approved; schedule it"
            )

        return OrchestratorDecision(route_to="finish", rationale="plan scheduled and complete")
