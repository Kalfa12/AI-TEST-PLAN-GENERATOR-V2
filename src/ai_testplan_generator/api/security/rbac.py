"""Role-based access control (M14).

Usage:

    @router.post("/projects/{project_id}/plans",
                 dependencies=[Depends(require("plan.generate"))])
    async def create_plan(...): ...

``require(permission)`` inspects the caller's project-scoped role (read from
the ``project_id`` path parameter) and raises 403 if the permission is not
granted. Global admins bypass all checks.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from ai_testplan_generator.api.deps import get_current_user, get_project_repo
from ai_testplan_generator.api.errors import AuthError
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User

PERMISSIONS: dict[str, set[str]] = {
    "project.read":    {"owner", "editor", "reviewer", "viewer"},
    "project.write":   {"owner", "editor"},
    "project.admin":   {"owner"},
    "document.read":   {"owner", "editor", "reviewer", "viewer"},
    "document.upload": {"owner", "editor"},
    "document.delete": {"owner", "editor"},
    "plan.generate":   {"owner", "editor"},
    "plan.read":       {"owner", "editor", "reviewer", "viewer"},
    "plan.approve":    {"owner", "reviewer"},
    "general_kb.read": {"admin"},
    "general_kb.write": {"admin"},
}


def require(permission: str) -> Callable[..., Awaitable[None]]:
    """Return a FastAPI dependency that enforces the given permission."""

    async def _dep(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    ) -> None:
        if current_user.is_admin:
            return

        allowed_roles = PERMISSIONS.get(permission, set())

        # Permissions restricted to global admin only.
        if allowed_roles == {"admin"}:
            raise AuthError("Forbidden: global admin required.")

        project_id: str | None = request.path_params.get("project_id")
        if not project_id:
            raise AuthError(f"Forbidden: '{permission}' requires a project context.")

        member = await project_repo.get_member(project_id, current_user.id)
        role_value: str | None = member.role.value if member else None
        if member is None:
            project = await project_repo.get_project(project_id)
            if project is not None and project.owner_id == current_user.id:
                role_value = "owner"
            else:
                raise AuthError(f"Forbidden: not a member of project '{project_id}'.")

        if role_value not in allowed_roles:
            raise AuthError(
                f"Forbidden: role '{role_value}' does not grant '{permission}'."
            )

    return _dep
