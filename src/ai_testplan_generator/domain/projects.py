"""Project and project-member domain models + async SQLite repository.

Schema is created on first connection (no external migration runner needed).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
import structlog

_log = structlog.get_logger(__name__)

DEFAULT_MONTHLY_BUDGET_USD = 50.0
DEFAULT_PROJECT_INDUSTRY = "generic"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    industry    TEXT NOT NULL DEFAULT 'generic',
    owner_id    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    archived_at TEXT,
    monthly_budget_usd REAL NOT NULL DEFAULT 50.0,
    budget_override_until TEXT,
    budget_override_usd REAL
);
CREATE TABLE IF NOT EXISTS project_members (
    project_id  TEXT NOT NULL REFERENCES projects(id),
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_pm_project ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_user    ON project_members(user_id);
"""


class ProjectRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class ProjectIndustry(StrEnum):
    GENERIC = "generic"
    AEROSPACE = "aerospace"
    AUTOMOTIVE = "automotive"
    MEDICAL = "medical"
    ENERGY = "energy"


@dataclass
class Project:
    id: str = field(default_factory=lambda: f"proj_{uuid4().hex[:10]}")
    name: str = ""
    description: str = ""
    industry: ProjectIndustry = ProjectIndustry.GENERIC
    owner_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: datetime | None = None
    monthly_budget_usd: float = DEFAULT_MONTHLY_BUDGET_USD
    budget_override_until: datetime | None = None
    budget_override_usd: float | None = None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


@dataclass
class ProjectMember:
    project_id: str
    user_id: str
    role: ProjectRole
    added_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRepository:
    """Async SQLite-backed CRUD for projects and members."""

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, *, db_path: str) -> "ProjectRepository":
        repo = cls(db_path=db_path)
        await repo._init()
        return repo

    async def _init(self) -> None:
        path_str = self._db_path
        if path_str != ":memory:":
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(path_str)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.executescript(_SCHEMA)
        await self._ensure_project_columns()
        await self._conn.commit()
        _log.info("project_repo_init", db_path=path_str)

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("ProjectRepository not initialised — call create() first")
        return self._conn

    async def _ensure_project_columns(self) -> None:
        async with self._db().execute("PRAGMA table_info(projects)") as cur:
            rows = await cur.fetchall()
        columns = {row[1] for row in rows}
        migrations = []
        if "industry" not in columns:
            migrations.append(
                "ALTER TABLE projects ADD COLUMN industry TEXT NOT NULL DEFAULT 'generic'"
            )
        if "monthly_budget_usd" not in columns:
            migrations.append(
                "ALTER TABLE projects ADD COLUMN monthly_budget_usd REAL NOT NULL DEFAULT 50.0"
            )
        if "budget_override_until" not in columns:
            migrations.append("ALTER TABLE projects ADD COLUMN budget_override_until TEXT")
        if "budget_override_usd" not in columns:
            migrations.append("ALTER TABLE projects ADD COLUMN budget_override_usd REAL")
        for sql in migrations:
            await self._db().execute(sql)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def create_project(
        self,
        name: str,
        description: str = "",
        owner_id: str = "",
        industry: ProjectIndustry = ProjectIndustry.GENERIC,
        monthly_budget_usd: float = DEFAULT_MONTHLY_BUDGET_USD,
    ) -> Project:
        proj = Project(
            name=name,
            description=description,
            owner_id=owner_id,
            industry=ProjectIndustry(industry),
            monthly_budget_usd=monthly_budget_usd,
        )
        await self._db().execute(
            """
            INSERT INTO projects
                (id, name, description, industry, owner_id, created_at, monthly_budget_usd)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                proj.id,
                proj.name,
                proj.description,
                proj.industry.value,
                proj.owner_id,
                proj.created_at.isoformat(),
                proj.monthly_budget_usd,
            ),
        )
        await self._db().commit()
        return proj

    async def get_project(self, project_id: str) -> Project | None:
        async with self._db().execute(
            """
            SELECT id,name,description,industry,owner_id,created_at,archived_at,
                   monthly_budget_usd,budget_override_until,budget_override_usd
            FROM projects WHERE id=?
            """,
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_project(row) if row else None

    async def list_projects(
        self,
        *,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        sql = (
            "SELECT id,name,description,industry,owner_id,created_at,archived_at,"
            "monthly_budget_usd,budget_override_until,budget_override_usd FROM projects"
        )
        params: tuple[Any, ...] = ()
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params = (*params, limit, offset)
        async with self._db().execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [_row_to_project(r) for r in rows]

    async def list_projects_for_user(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        sql = (
            "SELECT p.id,p.name,p.description,p.industry,p.owner_id,p.created_at,p.archived_at,"
            "p.monthly_budget_usd,p.budget_override_until,p.budget_override_usd "
            "FROM projects p "
            "JOIN project_members pm ON pm.project_id = p.id "
            "WHERE pm.user_id=?"
        )
        params: tuple[Any, ...] = (user_id,)
        if not include_archived:
            sql += " AND p.archived_at IS NULL"
        sql += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
        params = (*params, limit, offset)
        async with self._db().execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [_row_to_project(r) for r in rows]

    async def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        industry: ProjectIndustry | None = None,
    ) -> Project | None:
        proj = await self.get_project(project_id)
        if proj is None:
            return None
        new_name = name if name is not None else proj.name
        new_desc = description if description is not None else proj.description
        new_industry = ProjectIndustry(industry) if industry is not None else proj.industry
        await self._db().execute(
            "UPDATE projects SET name=?, description=?, industry=? WHERE id=?",
            (new_name, new_desc, new_industry.value, project_id),
        )
        await self._db().commit()
        proj.name = new_name
        proj.description = new_desc
        proj.industry = new_industry
        return proj

    async def update_project_budget(
        self,
        project_id: str,
        *,
        monthly_budget_usd: float,
        budget_override_until: datetime | None = None,
        budget_override_usd: float | None = None,
    ) -> Project | None:
        proj = await self.get_project(project_id)
        if proj is None:
            return None
        await self._db().execute(
            """
            UPDATE projects
            SET monthly_budget_usd=?, budget_override_until=?, budget_override_usd=?
            WHERE id=?
            """,
            (
                monthly_budget_usd,
                budget_override_until.isoformat() if budget_override_until else None,
                budget_override_usd,
                project_id,
            ),
        )
        await self._db().commit()
        proj.monthly_budget_usd = monthly_budget_usd
        proj.budget_override_until = budget_override_until
        proj.budget_override_usd = budget_override_usd
        return proj

    async def archive_project(self, project_id: str) -> bool:
        ts = datetime.now(timezone.utc).isoformat()
        async with self._db().execute(
            "UPDATE projects SET archived_at=? WHERE id=? AND archived_at IS NULL",
            (ts, project_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        return changed > 0

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def add_member(
        self, project_id: str, user_id: str, role: ProjectRole
    ) -> ProjectMember:
        member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
        await self._db().execute(
            "INSERT OR REPLACE INTO project_members (project_id,user_id,role,added_at) VALUES (?,?,?,?)",
            (project_id, user_id, role.value, member.added_at.isoformat()),
        )
        await self._db().commit()
        return member

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        async with self._db().execute(
            "DELETE FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        return changed > 0

    async def list_members(self, project_id: str) -> list[ProjectMember]:
        async with self._db().execute(
            "SELECT project_id,user_id,role,added_at FROM project_members WHERE project_id=?",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_member(r) for r in rows]

    async def get_member(
        self, project_id: str, user_id: str
    ) -> ProjectMember | None:
        async with self._db().execute(
            "SELECT project_id,user_id,role,added_at FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_member(row) if row else None

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


# ------------------------------------------------------------------
# Row mappers
# ------------------------------------------------------------------

def _row_to_project(
    row: tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str | None,
        float,
        str | None,
        float | None,
    ],
) -> Project:
    (
        pid,
        name,
        desc,
        industry,
        owner_id,
        created_at,
        archived_at,
        monthly_budget_usd,
        budget_override_until,
        budget_override_usd,
    ) = row
    return Project(
        id=pid,
        name=name,
        description=desc,
        industry=ProjectIndustry(industry or DEFAULT_PROJECT_INDUSTRY),
        owner_id=owner_id,
        created_at=datetime.fromisoformat(created_at),
        archived_at=datetime.fromisoformat(archived_at) if archived_at else None,
        monthly_budget_usd=float(monthly_budget_usd),
        budget_override_until=(
            datetime.fromisoformat(budget_override_until)
            if budget_override_until
            else None
        ),
        budget_override_usd=(
            float(budget_override_usd) if budget_override_usd is not None else None
        ),
    )


def _row_to_member(
    row: tuple[str, str, str, str],
) -> ProjectMember:
    project_id, user_id, role, added_at = row
    return ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=ProjectRole(role),
        added_at=datetime.fromisoformat(added_at),
    )
