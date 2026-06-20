"""Project access helpers shared by route handlers."""

from __future__ import annotations

from ai_testplan_generator.api.errors import AuthError
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User


async def ensure_project_access(
    *,
    project_id: str | None,
    current_user: User,
    project_repo: ProjectRepository,
) -> None:
    if current_user.is_admin:
        return
    if not project_id:
        raise AuthError("Forbidden: project context is required.")
    member = await project_repo.get_member(project_id, current_user.id)
    if member is not None:
        return
    project = await project_repo.get_project(project_id)
    if project is not None and project.owner_id == current_user.id:
        return
    raise AuthError(f"Forbidden: not a member of project '{project_id}'.")
