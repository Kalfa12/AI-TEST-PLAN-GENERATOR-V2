"""Projects and members endpoints (M10).

POST   /projects                           create project
GET    /projects                           list projects
GET    /projects/{id}                      get project
PATCH  /projects/{id}                      update name/description
DELETE /projects/{id}                      archive (soft delete)
POST   /projects/{id}/members              invite member
DELETE /projects/{id}/members/{user_id}    remove member
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ai_testplan_generator.api.deps import get_project_repo
from ai_testplan_generator.api.errors import ConflictError, NotFoundError
from ai_testplan_generator.domain.projects import (
    Project,
    ProjectMember,
    ProjectRepository,
    ProjectRole,
)

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    owner_id: str = ""


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class AddMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: ProjectRole = ProjectRole.VIEWER


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    created_at: str
    archived_at: str | None = None

    @classmethod
    def from_project(cls, p: Project) -> "ProjectResponse":
        return cls(
            id=p.id,
            name=p.name,
            description=p.description,
            owner_id=p.owner_id,
            created_at=p.created_at.isoformat(),
            archived_at=p.archived_at.isoformat() if p.archived_at else None,
        )


class MemberResponse(BaseModel):
    project_id: str
    user_id: str
    role: str
    added_at: str

    @classmethod
    def from_member(cls, m: ProjectMember) -> "MemberResponse":
        return cls(
            project_id=m.project_id,
            user_id=m.user_id,
            role=m.role.value,
            added_at=m.added_at.isoformat(),
        )


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201, response_model=ProjectResponse, summary="Create a project")
async def create_project(
    body: CreateProjectRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ProjectResponse:
    proj = await repo.create_project(
        name=body.name, description=body.description, owner_id=body.owner_id
    )
    _log.info("project_created", project_id=proj.id, name=proj.name)
    return ProjectResponse.from_project(proj)


@router.get("", response_model=ProjectListResponse, summary="List projects")
async def list_projects(
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
) -> ProjectListResponse:
    items = await repo.list_projects(
        include_archived=include_archived, limit=limit, offset=offset
    )
    return ProjectListResponse(items=[ProjectResponse.from_project(p) for p in items],
                               total=len(items))


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get a project")
async def get_project(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ProjectResponse:
    proj = await repo.get_project(project_id)
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    return ProjectResponse.from_project(proj)


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Update project metadata")
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ProjectResponse:
    proj = await repo.update_project(
        project_id, name=body.name, description=body.description
    )
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    return ProjectResponse.from_project(proj)


@router.delete("/{project_id}", status_code=204, summary="Archive a project")
async def archive_project(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> None:
    ok = await repo.archive_project(project_id)
    if not ok:
        raise NotFoundError(f"Project '{project_id}' not found or already archived.")


@router.post(
    "/{project_id}/members",
    status_code=201,
    response_model=MemberResponse,
    summary="Add a member to a project",
)
async def add_member(
    project_id: str,
    body: AddMemberRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> MemberResponse:
    proj = await repo.get_project(project_id)
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    member = await repo.add_member(project_id, body.user_id, body.role)
    return MemberResponse.from_member(member)


@router.get(
    "/{project_id}/members",
    response_model=list[MemberResponse],
    summary="List project members",
)
async def list_members(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> list[MemberResponse]:
    proj = await repo.get_project(project_id)
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    members = await repo.list_members(project_id)
    return [MemberResponse.from_member(m) for m in members]


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=204,
    summary="Remove a member from a project",
)
async def remove_member(
    project_id: str,
    user_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> None:
    ok = await repo.remove_member(project_id, user_id)
    if not ok:
        raise NotFoundError(f"Member '{user_id}' not found in project '{project_id}'.")
