from __future__ import annotations

import aiosqlite
import pytest

from ai_testplan_generator.domain.projects import (
    ProjectIndustry,
    ProjectRepository,
)


@pytest.mark.asyncio
async def test_project_repo_migrates_old_schema_to_generic_industry(tmp_path) -> None:
    db_path = str(tmp_path / "old-projects.db")
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """
            CREATE TABLE projects (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                owner_id    TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                archived_at TEXT,
                monthly_budget_usd REAL NOT NULL DEFAULT 50.0,
                budget_override_until TEXT,
                budget_override_usd REAL
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO projects
                (id, name, description, owner_id, created_at, monthly_budget_usd)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "proj_old",
                "Legacy project",
                "",
                "usr_owner",
                "2026-01-01T00:00:00+00:00",
                50.0,
            ),
        )
        await conn.commit()

    repo = await ProjectRepository.create(db_path=db_path)
    try:
        project = await repo.get_project("proj_old")
        assert project is not None
        assert project.industry == ProjectIndustry.GENERIC
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_project_repo_creates_and_updates_industry(tmp_path) -> None:
    repo = await ProjectRepository.create(db_path=str(tmp_path / "app.db"))
    try:
        project = await repo.create_project(
            "Automotive validation",
            industry=ProjectIndustry.AUTOMOTIVE,
        )
        assert project.industry == ProjectIndustry.AUTOMOTIVE

        updated = await repo.update_project(
            project.id,
            industry=ProjectIndustry.AEROSPACE,
        )

        assert updated is not None
        assert updated.industry == ProjectIndustry.AEROSPACE
        reloaded = await repo.get_project(project.id)
        assert reloaded is not None
        assert reloaded.industry == ProjectIndustry.AEROSPACE
    finally:
        await repo.close()
