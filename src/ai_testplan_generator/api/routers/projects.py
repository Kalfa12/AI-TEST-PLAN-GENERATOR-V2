"""Projects and members endpoints (M10).

POST   /projects                           create project
GET    /projects                           list projects
GET    /projects/{id}                      get project
PATCH  /projects/{id}                      update name/description
DELETE /projects/{id}                      archive (soft delete)
DELETE /projects/{id}/permanent            permanently delete
POST   /projects/{id}/members              invite member
DELETE /projects/{id}/members/{user_id}    remove member
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ai_testplan_generator.api.deps import (
    get_blob_store,
    get_brain,
    get_current_user,
    get_project_repo,
    get_settings,
)
from ai_testplan_generator.api.errors import NotFoundError, ValidationError
from ai_testplan_generator.api.security.rbac import require
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import (
    DEFAULT_MONTHLY_BUDGET_USD,
    Project,
    ProjectIndustry,
    ProjectMember,
    ProjectRepository,
    ProjectRole,
)
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore
from ai_testplan_generator.telemetry.cost import get_project_spend_usd

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    industry: ProjectIndustry = ProjectIndustry.GENERIC
    monthly_budget_usd: float = Field(default=DEFAULT_MONTHLY_BUDGET_USD, ge=0)
    # Deprecated input kept for old clients; the server always uses current_user.id.
    owner_id: str | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    industry: ProjectIndustry | None = None


class AddMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: ProjectRole = ProjectRole.VIEWER


class UpdateProjectBudgetRequest(BaseModel):
    monthly_budget_usd: float = Field(ge=0)
    budget_override_usd: float | None = Field(default=None, ge=0)
    budget_override_until: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    industry: ProjectIndustry
    owner_id: str
    created_at: str
    archived_at: str | None = None
    monthly_budget_usd: float
    budget_override_until: str | None = None
    budget_override_usd: float | None = None
    current_month_spend_usd: float = 0.0

    @classmethod
    def from_project(
        cls, p: Project, *, current_month_spend_usd: float = 0.0
    ) -> ProjectResponse:
        return cls(
            id=p.id,
            name=p.name,
            description=p.description,
            industry=p.industry,
            owner_id=p.owner_id,
            created_at=p.created_at.isoformat(),
            archived_at=p.archived_at.isoformat() if p.archived_at else None,
            monthly_budget_usd=p.monthly_budget_usd,
            budget_override_until=(
                p.budget_override_until.isoformat()
                if p.budget_override_until
                else None
            ),
            budget_override_usd=p.budget_override_usd,
            current_month_spend_usd=current_month_spend_usd,
        )


class MemberResponse(BaseModel):
    project_id: str
    user_id: str
    role: str
    added_at: str

    @classmethod
    def from_member(cls, m: ProjectMember) -> MemberResponse:
        return cls(
            project_id=m.project_id,
            user_id=m.user_id,
            role=m.role.value,
            added_at=m.added_at.isoformat(),
        )


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse] = Field(default_factory=list)
    total: int = 0


async def _project_response(p: Project, settings: Settings) -> ProjectResponse:
    spend = await get_project_spend_usd(settings.app_db_path, project_id=p.id)
    return ProjectResponse.from_project(p, current_month_spend_usd=spend)


def _parse_override_until(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        override_until = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("budget_override_until must be an ISO-8601 datetime.") from exc
    if override_until.tzinfo is None:
        override_until = override_until.replace(tzinfo=timezone.utc)
    return override_until.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201, response_model=ProjectResponse, summary="Create a project")
async def create_project(
    body: CreateProjectRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectResponse:
    proj = await repo.create_project(
        name=body.name,
        description=body.description,
        owner_id=current_user.id,
        industry=body.industry,
        monthly_budget_usd=body.monthly_budget_usd,
    )
    await repo.add_member(proj.id, current_user.id, ProjectRole.OWNER)
    _log.info(
        "project_created",
        project_id=proj.id,
        name=proj.name,
        owner_id=current_user.id,
    )
    return await _project_response(proj, settings)


@router.get("", response_model=ProjectListResponse, summary="List projects")
async def list_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
) -> ProjectListResponse:
    if current_user.is_admin:
        items = await repo.list_projects(
            include_archived=include_archived, limit=limit, offset=offset
        )
    else:
        items = await repo.list_projects_for_user(
            current_user.id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
    return ProjectListResponse(
        items=[await _project_response(p, settings) for p in items],
        total=len(items),
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get a project",
    dependencies=[Depends(require("project.read"))],
)
async def get_project(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectResponse:
    proj = await repo.get_project(project_id)
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    return await _project_response(proj, settings)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project metadata",
    dependencies=[Depends(require("project.write"))],
)
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectResponse:
    proj = await repo.update_project(
        project_id,
        name=body.name,
        description=body.description,
        industry=body.industry,
    )
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    return await _project_response(proj, settings)


@router.patch(
    "/{project_id}/budget",
    response_model=ProjectResponse,
    summary="Update project LLM budget",
    dependencies=[Depends(require("project.admin"))],
)
async def update_project_budget(
    project_id: str,
    body: UpdateProjectBudgetRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectResponse:
    if (body.budget_override_usd is None) != (body.budget_override_until is None):
        raise ValidationError(
            "budget_override_usd and budget_override_until must be set together."
        )
    override_until = _parse_override_until(body.budget_override_until)
    proj = await repo.update_project_budget(
        project_id,
        monthly_budget_usd=body.monthly_budget_usd,
        budget_override_usd=body.budget_override_usd,
        budget_override_until=override_until,
    )
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    return await _project_response(proj, settings)


@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Archive a project",
    dependencies=[Depends(require("project.admin"))],
)
async def archive_project(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> None:
    ok = await repo.archive_project(project_id)
    if not ok:
        raise NotFoundError(f"Project '{project_id}' not found or already archived.")


@router.delete(
    "/{project_id}/permanent",
    status_code=204,
    summary="Permanently delete a project and its artefacts",
    dependencies=[Depends(require("project.admin"))],
)
async def delete_project_permanently(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    brain: Annotated[Brain, Depends(get_brain)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> None:
    proj = await repo.get_project(project_id)
    if proj is None:
        raise NotFoundError(f"Project '{project_id}' not found.")

    docs = await brain.memory.get_documents_for_project(project_id)
    for doc in docs:
        try:
            await blob_store.delete(doc.source_uri)
        except Exception:
            _log.warning(
                "project_blob_delete_failed",
                project_id=project_id,
                document_id=doc.id,
                source_uri=doc.source_uri,
            )
    await brain.memory.delete_project_artefacts(project_id)

    ok = await repo.delete_project(project_id)
    if not ok:
        raise NotFoundError(f"Project '{project_id}' not found.")
    _log.info("project_deleted", project_id=project_id)


@router.post(
    "/{project_id}/members",
    status_code=201,
    response_model=MemberResponse,
    summary="Add a member to a project",
    dependencies=[Depends(require("project.admin"))],
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
    dependencies=[Depends(require("project.read"))],
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
    dependencies=[Depends(require("project.admin"))],
)
async def remove_member(
    project_id: str,
    user_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> None:
    ok = await repo.remove_member(project_id, user_id)
    if not ok:
        raise NotFoundError(f"Member '{user_id}' not found in project '{project_id}'.")
