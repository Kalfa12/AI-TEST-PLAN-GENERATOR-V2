"""Planning resources, schedules, and test-case follow-up endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ai_testplan_generator.agents.planner import PlannerAgent
from ai_testplan_generator.api.deps import get_brain, get_current_user
from ai_testplan_generator.api.errors import NotFoundError, ValidationError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.models import Resource, TestCaseStatus, TestPlan, TestSchedule
from ai_testplan_generator.pipelines.brain import Brain

router = APIRouter(tags=["planning"])


class CreateResourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    service: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    availability_pct: int = Field(default=100, ge=0, le=100)


class UpdateResourceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    service: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    availability_pct: int | None = Field(default=None, ge=0, le=100)


class ResourceListResponse(BaseModel):
    items: list[Resource] = Field(default_factory=list)
    total: int = 0


class UpdateTestCaseStatusRequest(BaseModel):
    status: TestCaseStatus
    status_note: str | None = Field(default=None, max_length=1000)


class TestCaseStatusResponse(BaseModel):
    plan_id: str
    test_case_id: str
    status: TestCaseStatus
    status_note: str | None = None


@router.get(
    "/projects/{project_id}/resources",
    response_model=ResourceListResponse,
    summary="List project planning resources",
    dependencies=[Depends(require("project.read"))],
)
async def list_resources(
    project_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> ResourceListResponse:
    resources = await brain.memory.list_resources_for_project(project_id)
    return ResourceListResponse(items=resources, total=len(resources))


@router.post(
    "/projects/{project_id}/resources",
    status_code=201,
    response_model=Resource,
    summary="Create a project planning resource",
    dependencies=[Depends(require("project.write"))],
)
async def create_resource(
    project_id: str,
    body: CreateResourceRequest,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    brain: Annotated[Brain, Depends(get_brain)],
) -> Resource:
    resource = Resource(
        project_id=project_id,
        name=body.name,
        service=body.service,
        role=body.role,
        availability_pct=body.availability_pct,
    )
    await brain.memory.register_resource(resource)
    return resource


@router.patch(
    "/projects/{project_id}/resources/{resource_id}",
    response_model=Resource,
    summary="Update a project planning resource",
    dependencies=[Depends(require("project.write"))],
)
async def update_resource(
    project_id: str,
    resource_id: str,
    body: UpdateResourceRequest,
    brain: Annotated[Brain, Depends(get_brain)],
) -> Resource:
    existing = await brain.memory.get_resource(project_id, resource_id)
    if existing is None:
        raise NotFoundError(f"Resource '{resource_id}' not found.")
    updated = existing.model_copy(
        update={
            "name": body.name if body.name is not None else existing.name,
            "service": body.service if body.service is not None else existing.service,
            "role": body.role if body.role is not None else existing.role,
            "availability_pct": (
                body.availability_pct
                if body.availability_pct is not None
                else existing.availability_pct
            ),
        }
    )
    await brain.memory.register_resource(updated)
    return updated


@router.delete(
    "/projects/{project_id}/resources/{resource_id}",
    status_code=204,
    summary="Delete a project planning resource",
    dependencies=[Depends(require("project.write"))],
)
async def delete_resource(
    project_id: str,
    resource_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> None:
    ok = await brain.memory.delete_resource(project_id, resource_id)
    if not ok:
        raise NotFoundError(f"Resource '{resource_id}' not found.")


@router.post(
    "/projects/{project_id}/plans/{plan_id}/schedule",
    response_model=TestSchedule,
    summary="Generate or refresh a plan schedule from project resources",
    dependencies=[Depends(require("plan.generate"))],
)
async def schedule_plan(
    project_id: str,
    plan_id: str,
    brain: Annotated[Brain, Depends(get_brain)],
) -> TestSchedule:
    plan = await brain.memory.get_test_plan(plan_id)
    if plan is None or plan.project_id != project_id:
        raise NotFoundError(f"Plan '{plan_id}' not found.")
    resources = await brain.memory.list_resources_for_project(project_id)
    ctx = brain.context(session_id=f"sess_schedule_{uuid4().hex[:10]}", project_id=project_id)
    schedule = await PlannerAgent(ctx).invoke(
        PlannerAgent.Input(plan=plan, resources=resources)
    )
    await brain.memory.register_test_plan(plan)
    return schedule


@router.patch(
    "/projects/{project_id}/plans/{plan_id}/test-cases/{test_case_id}/status",
    response_model=TestCaseStatusResponse,
    summary="Update test-case execution status",
    dependencies=[Depends(require("plan.generate"))],
)
async def update_test_case_status(
    project_id: str,
    plan_id: str,
    test_case_id: str,
    body: UpdateTestCaseStatusRequest,
    brain: Annotated[Brain, Depends(get_brain)],
) -> TestCaseStatusResponse:
    repo = brain.memory.artifact_repo
    if repo is None:
        raise ValidationError("Plan persistence is not configured.")
    plan = await repo.update_test_case_status(
        project_id=project_id,
        plan_id=plan_id,
        test_case_id=test_case_id,
        status=body.status,
        status_note=body.status_note,
    )
    if plan is None:
        raise NotFoundError(f"Test case '{test_case_id}' not found in plan '{plan_id}'.")
    await brain.memory.register_test_plan(plan)
    return TestCaseStatusResponse(
        plan_id=plan_id,
        test_case_id=test_case_id,
        status=body.status,
        status_note=body.status_note,
    )
