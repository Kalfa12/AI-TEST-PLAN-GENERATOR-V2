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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    owner_id    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    archived_at TEXT
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


@dataclass
class Project:
    id: str = field(default_factory=lambda: f"proj_{uuid4().hex[:10]}")
    name: str = ""
    description: str = ""
    owner_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: datetime | None = None

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
        await self._conn.commit()
        _log.info("project_repo_init", db_path=path_str)

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("ProjectRepository not initialised — call create() first")
        return self._conn

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def create_project(
        self, name: str, description: str = "", owner_id: str = ""
    ) -> Project:
        proj = Project(name=name, description=description, owner_id=owner_id)
        await self._db().execute(
            "INSERT INTO projects (id, name, description, owner_id, created_at) VALUES (?,?,?,?,?)",
            (proj.id, proj.name, proj.description, proj.owner_id, proj.created_at.isoformat()),
        )
        await self._db().commit()
        return proj

    async def get_project(self, project_id: str) -> Project | None:
        async with self._db().execute(
            "SELECT id,name,description,owner_id,created_at,archived_at FROM projects WHERE id=?",
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
        sql = "SELECT id,name,description,owner_id,created_at,archived_at FROM projects"
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
            "SELECT p.id,p.name,p.description,p.owner_id,p.created_at,p.archived_at "
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
    ) -> Project | None:
        proj = await self.get_project(project_id)
        if proj is None:
            return None
        new_name = name if name is not None else proj.name
        new_desc = description if description is not None else proj.description
        await self._db().execute(
            "UPDATE projects SET name=?, description=? WHERE id=?",
            (new_name, new_desc, project_id),
        )
        await self._db().commit()
        proj.name = new_name
        proj.description = new_desc
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
    row: tuple[str, str, str, str, str, str | None],
) -> Project:
    pid, name, desc, owner_id, created_at, archived_at = row
    return Project(
        id=pid,
        name=name,
        description=desc,
        owner_id=owner_id,
        created_at=datetime.fromisoformat(created_at),
        archived_at=datetime.fromisoformat(archived_at) if archived_at else None,
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
