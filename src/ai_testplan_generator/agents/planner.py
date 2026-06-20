"""PlannerAgent - builds the TestSchedule with milestones + resource assignment."""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from ai_testplan_generator.agents.base import BaseAgent
from ai_testplan_generator.llm import ChatMessage
from ai_testplan_generator.models import (
    Milestone,
    Resource,
    TestCaseStatus,
    TestPlan,
    TestSchedule,
)
from ai_testplan_generator.models.planning import ScheduledAssignment
from ai_testplan_generator.prompts.library import PLANNER_SYSTEM, with_industry_context


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
        if not inp.resources:
            schedule = TestSchedule(plan_id=inp.plan.id)
            inp.plan.schedule = schedule
            await self.ctx.memory.log_event(
                self.ctx.session_id,
                actor=self.name,
                kind="planning_skipped",
                content=(
                    "No planning resources were configured; returning an empty "
                    "schedule instead of fabricating assignments."
                ),
            )
            return schedule

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
        industry = await self.ctx.project_industry()
        messages = [
            ChatMessage(
                role="system",
                content=with_industry_context(PLANNER_SYSTEM, industry),
            ),
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
        valid_test_case_ids = {tc.id for tc in inp.plan.test_cases}
        resource_by_id = {resource.id: resource for resource in inp.resources}
        rejected: list[str] = []
        for a in draft.assignments:
            if a.test_case_id not in valid_test_case_ids:
                rejected.append(f"unknown test case {a.test_case_id}")
                continue
            resource_ids = [rid for rid in a.resource_ids if rid in resource_by_id]
            unknown_resource_ids = sorted(set(a.resource_ids) - set(resource_ids))
            if unknown_resource_ids:
                rejected.append(
                    f"{a.test_case_id}: unknown resources {', '.join(unknown_resource_ids)}"
                )
            if not resource_ids:
                continue
            if a.end < a.start:
                rejected.append(f"{a.test_case_id}: end before start")
                continue
            schedule.assignments[a.test_case_id] = ScheduledAssignment(
                start=a.start,
                end=a.end,
                resource_ids=resource_ids,
                service=a.service,
            )
        if rejected:
            await self.ctx.memory.log_event(
                self.ctx.session_id,
                actor=self.name,
                kind="planning_warning",
                content="\n".join(rejected),
            )
        for tc in inp.plan.test_cases:
            assignment = schedule.assignments.get(tc.id)
            if assignment is None:
                continue
            tc.status = TestCaseStatus.PLANNED
            tc.assignee = ", ".join(
                resource_by_id[rid].name for rid in assignment.resource_ids
            )
        inp.plan.schedule = schedule
        return schedule
