"""Project-level LLM budget enforcement helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_testplan_generator.api.errors import BudgetExceededError
from ai_testplan_generator.telemetry.cost import get_project_spend_usd


async def enforce_project_llm_budget(
    *,
    settings: Any | None,
    project_repo: Any | None,
    project_id: str | None,
) -> None:
    if settings is None or project_repo is None or project_id is None:
        return

    project = await project_repo.get_project(project_id)
    if project is None:
        return

    effective_budget = float(project.monthly_budget_usd)
    if (
        project.budget_override_until is not None
        and project.budget_override_usd is not None
    ):
        now = datetime.now(timezone.utc)
        override_until = project.budget_override_until
        if override_until.tzinfo is None:
            override_until = override_until.replace(tzinfo=timezone.utc)
        if override_until >= now:
            effective_budget = float(project.budget_override_usd)

    spent = await get_project_spend_usd(settings.app_db_path, project_id=project_id)
    if spent >= effective_budget:
        raise BudgetExceededError(
            "Project monthly LLM budget exceeded "
            f"(${spent:.4f} spent of ${effective_budget:.2f})."
        )
