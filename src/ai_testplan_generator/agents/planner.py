"""PlannerAgent - builds the TestSchedule with milestones + resource assignment."""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.models import Milestone, Resource, TestPlan, TestSchedule
from ai_testplan_generator.models.planning import ScheduledAssignment
from ai_testplan_generator.prompts.library import PLANNER_SYSTEM


class _PlanInput(BaseModel):
    plan: TestPlan
    resources: list[Resource] = Field(default_factory=list)
    start_date: date | None = None


class _ScheduledAssignmentDraft(BaseModel):
    test_case_id: str
    start: date
    end: date
    resource_ids: list[str] = Field(default_factory=list)
    service: str | None = None


class _PlannerOutput(BaseModel):
    milestones: list[Milestone] = Field(default_factory=list)
    assignments: list[_ScheduledAssignmentDraft] = Field(default_factory=list)


class PlannerAgent(BaseAgent[_PlanInput, TestSchedule]):
    name = "planner"
    Input = _PlanInput

    async def run(self, inp: _PlanInput) -> TestSchedule:
        start = inp.start_date or (date.today() + timedelta(days=7))
        tc_blob = [
            f"- [{tc.id}] {tc.title} "
            f"(risk={tc.risk_level}, dur_min={tc.estimated_duration_minutes}, "
            f"equip={tc.equipment})"
            for tc in inp.plan.test_cases
        ]
        res_blob = [
            f"- [{r.id}] {r.name} - service={r.service} role={r.role} avail={r.availability_pct}%"
            for r in inp.resources
        ]
        messages = [
            ChatMessage(role="system", content=PLANNER_SYSTEM),
            ChatMessage(
                role="user",
                content=(
                    f"Plan: {inp.plan.title}\nStart date: {start.isoformat()}\n\n"
                    f"Resources:\n" + "\n".join(res_blob) + "\n\n"
                    f"Test cases:\n" + "\n".join(tc_blob)
                ),
            ),
        ]
        draft = await self.ctx.llm.complete_structured(
            messages, _PlannerOutput, role="balanced", temperature=0.1
        )

        schedule = TestSchedule(plan_id=inp.plan.id, milestones=draft.milestones)
        for a in draft.assignments:
            schedule.assignments[a.test_case_id] = ScheduledAssignment(
                start=a.start,
                end=a.end,
                resource_ids=a.resource_ids,
                service=a.service,
            )
        return schedule
