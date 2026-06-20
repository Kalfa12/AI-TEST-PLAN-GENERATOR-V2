"""Durable repository for product artefacts.

The vector store and graph store are retrieval indexes. This repository is the
SQLite source of truth for the typed product objects the API has to list,
reload, and export after a process restart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from ai_testplan_generator.domain.chat_actions import ChatAction, PendingChatAction
from ai_testplan_generator.models import (
    Chunk,
    Document,
    Requirement,
    Resource,
    Section,
    TestCase,
    TestCaseStatus,
    TestPlan,
)

_log = structlog.get_logger(__name__)

_MIGRATION_ID = "artifact_store_v1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    source_uri  TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(scope);

CREATE TABLE IF NOT EXISTS sections (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    parent_id   TEXT,
    title       TEXT NOT NULL,
    level       INTEGER NOT NULL,
    page_start  INTEGER,
    page_end    INTEGER,
    json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sections_document ON sections(document_id);

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    section_id  TEXT,
    kind        TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    page_start  INTEGER,
    page_end    INTEGER,
    json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_id);

CREATE TABLE IF NOT EXISTS requirements (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT,
    source_document_id TEXT NOT NULL,
    kind               TEXT NOT NULL,
    priority           INTEGER NOT NULL,
    json               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requirements_project ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_requirements_document ON requirements(source_document_id);

CREATE TABLE IF NOT EXISTS test_plans (
    id           TEXT PRIMARY KEY,
    project_id   TEXT,
    title        TEXT NOT NULL,
    detail_level TEXT NOT NULL,
    json         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_test_plans_project ON test_plans(project_id);

CREATE TABLE IF NOT EXISTS test_cases (
    id      TEXT PRIMARY KEY,
    plan_id TEXT,
    json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_test_cases_plan ON test_cases(plan_id);

CREATE TABLE IF NOT EXISTS resources (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    name             TEXT NOT NULL,
    service          TEXT NOT NULL,
    role             TEXT,
    availability_pct INTEGER NOT NULL,
    json             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resources_project ON resources(project_id);

CREATE TABLE IF NOT EXISTS pending_chat_actions (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    action      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_chat_session
    ON pending_chat_actions(session_id, user_id, consumed_at, expires_at);

CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    user_id      TEXT,
    project_id   TEXT,
    action       TEXT NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    status       INTEGER NOT NULL,
    ip           TEXT,
    user_agent   TEXT,
    metadata     TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_events(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON audit_events(action, ts);
"""


@dataclass
class ArtifactSnapshot:
    documents: list[Document] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    test_plans: list[TestPlan] = field(default_factory=list)
    test_cases: list[tuple[TestCase, str | None]] = field(default_factory=list)


class ArtifactRepository:
    """Async SQLite-backed persistence for documents, requirements, and plans."""

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, *, db_path: str) -> "ArtifactRepository":
        repo = cls(db_path=db_path)
        await repo._init()
        return repo

    async def _init(self) -> None:
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.executescript(_SCHEMA)
        await self._record_migration(_MIGRATION_ID)
        await self._conn.commit()
        _log.info("artifact_repo_init", db_path=self._db_path)

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("ArtifactRepository not initialised - call create() first")
        return self._conn

    async def _record_migration(self, migration_id: str) -> None:
        await self._db().execute(
            "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (migration_id, datetime.now(timezone.utc).isoformat()),
        )

    async def save_document(self, doc: Document) -> None:
        await self._db().execute(
            """
            INSERT OR REPLACE INTO documents
                (id, project_id, scope, kind, title, sha256, source_uri, ingested_at, json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.id,
                doc.project_id,
                doc.scope,
                doc.kind.value,
                doc.title,
                doc.sha256,
                doc.source_uri,
                doc.ingested_at.isoformat(),
                doc.model_dump_json(),
            ),
        )
        await self._db().commit()

    async def save_sections(self, sections: list[Section]) -> None:
        if not sections:
            return
        await self._db().executemany(
            """
            INSERT OR REPLACE INTO sections
                (id, document_id, parent_id, title, level, page_start, page_end, json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    sec.id,
                    sec.document_id,
                    sec.parent_id,
                    sec.title,
                    sec.level,
                    sec.page_start,
                    sec.page_end,
                    sec.model_dump_json(),
                )
                for sec in sections
            ],
        )
        await self._db().commit()

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        await self._db().executemany(
            """
            INSERT OR REPLACE INTO chunks
                (id, document_id, section_id, kind, token_count, page_start, page_end, json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ch.id,
                    ch.document_id,
                    ch.section_id,
                    ch.kind.value,
                    ch.token_count,
                    ch.page_start,
                    ch.page_end,
                    ch.model_dump_json(),
                )
                for ch in chunks
            ],
        )
        await self._db().commit()

    async def save_requirements(self, requirements: list[Requirement]) -> None:
        if not requirements:
            return
        await self._db().executemany(
            """
            INSERT OR REPLACE INTO requirements
                (id, project_id, source_document_id, kind, priority, json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    req.id,
                    req.project_id,
                    req.source_document_id,
                    req.kind.value,
                    req.priority,
                    req.model_dump_json(),
                )
                for req in requirements
            ],
        )
        await self._db().commit()

    async def save_resource(self, resource: Resource) -> None:
        if resource.project_id is None:
            raise ValueError("Resource must have a project_id.")
        await self._db().execute(
            """
            INSERT OR REPLACE INTO resources
                (id, project_id, name, service, role, availability_pct, json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource.id,
                resource.project_id,
                resource.name,
                resource.service,
                resource.role,
                resource.availability_pct,
                resource.model_dump_json(),
            ),
        )
        await self._db().commit()

    async def list_resources(self, project_id: str) -> list[Resource]:
        rows = await self._fetch_all(
            "SELECT json FROM resources WHERE project_id=? ORDER BY name COLLATE NOCASE",
            (project_id,),
        )
        return [Resource.model_validate_json(row[0]) for row in rows]

    async def get_resource(self, project_id: str, resource_id: str) -> Resource | None:
        rows = await self._fetch_all(
            "SELECT json FROM resources WHERE project_id=? AND id=?",
            (project_id, resource_id),
        )
        if not rows:
            return None
        return Resource.model_validate_json(rows[0][0])

    async def delete_resource(self, project_id: str, resource_id: str) -> bool:
        async with self._db().execute(
            "DELETE FROM resources WHERE project_id=? AND id=?",
            (project_id, resource_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        return changed > 0

    async def save_pending_chat_action(self, action: PendingChatAction) -> None:
        await self._db().execute(
            """
            INSERT OR REPLACE INTO pending_chat_actions
                (id, session_id, user_id, project_id, action, payload,
                 created_at, expires_at, consumed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action.id,
                action.session_id,
                action.user_id,
                action.project_id,
                action.action.value,
                json.dumps(action.payload),
                action.created_at.isoformat(),
                action.expires_at.isoformat(),
                action.consumed_at.isoformat() if action.consumed_at else None,
            ),
        )
        await self._db().commit()

    async def get_pending_chat_action(
        self,
        *,
        session_id: str,
        user_id: str,
        action_id: str | None = None,
    ) -> PendingChatAction | None:
        now = datetime.now(timezone.utc).isoformat()
        if action_id is None:
            rows = await self._fetch_all(
                """
                SELECT id, session_id, user_id, project_id, action, payload,
                       created_at, expires_at, consumed_at
                FROM pending_chat_actions
                WHERE session_id=? AND user_id=? AND consumed_at IS NULL AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id, user_id, now),
            )
        else:
            rows = await self._fetch_all(
                """
                SELECT id, session_id, user_id, project_id, action, payload,
                       created_at, expires_at, consumed_at
                FROM pending_chat_actions
                WHERE id=? AND session_id=? AND user_id=?
                      AND consumed_at IS NULL AND expires_at > ?
                LIMIT 1
                """,
                (action_id, session_id, user_id, now),
            )
        if not rows:
            return None
        return _row_to_pending_chat_action(rows[0])

    async def consume_pending_chat_action(self, action_id: str) -> None:
        await self._db().execute(
            "UPDATE pending_chat_actions SET consumed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), action_id),
        )
        await self._db().commit()

    async def record_audit_event(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
        action: str,
        target_type: str | None,
        target_id: str | None,
        status: int = 200,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._db().execute(
            """
            INSERT INTO audit_events
                (ts, user_id, project_id, action, target_type, target_id, status, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                user_id,
                project_id,
                action,
                target_type,
                target_id,
                status,
                json.dumps(metadata or {}),
            ),
        )
        await self._db().commit()

    async def save_test_cases(
        self, test_cases: list[TestCase], *, plan_id: str | None = None
    ) -> None:
        if not test_cases:
            return
        await self._db().executemany(
            "INSERT OR REPLACE INTO test_cases (id, plan_id, json) VALUES (?, ?, ?)",
            [(tc.id, plan_id, tc.model_dump_json()) for tc in test_cases],
        )
        await self._db().commit()

    async def save_test_plan(self, plan: TestPlan) -> None:
        await self._db().execute(
            """
            INSERT OR REPLACE INTO test_plans (id, project_id, title, detail_level, json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                plan.id,
                plan.project_id,
                plan.title,
                plan.detail_level.value,
                plan.model_dump_json(),
            ),
        )
        await self.save_test_cases(plan.test_cases, plan_id=plan.id)
        await self._db().commit()

    async def load_snapshot(self) -> ArtifactSnapshot:
        return ArtifactSnapshot(
            documents=[
                Document.model_validate_json(row[0])
                for row in await self._fetch_all("SELECT json FROM documents")
            ],
            sections=[
                Section.model_validate_json(row[0])
                for row in await self._fetch_all("SELECT json FROM sections")
            ],
            chunks=[
                Chunk.model_validate_json(row[0])
                for row in await self._fetch_all("SELECT json FROM chunks")
            ],
            requirements=[
                Requirement.model_validate_json(row[0])
                for row in await self._fetch_all("SELECT json FROM requirements")
            ],
            resources=[
                Resource.model_validate_json(row[0])
                for row in await self._fetch_all("SELECT json FROM resources")
            ],
            test_plans=[
                TestPlan.model_validate_json(row[0])
                for row in await self._fetch_all("SELECT json FROM test_plans")
            ],
            test_cases=[
                (TestCase.model_validate_json(row[0]), row[1])
                for row in await self._fetch_all("SELECT json, plan_id FROM test_cases")
            ],
        )

    async def list_documents(self, project_id: str | None) -> list[Document]:
        rows = await self._fetch_all(
            "SELECT json FROM documents WHERE project_id IS ? ORDER BY ingested_at DESC",
            (project_id,),
        )
        return [Document.model_validate_json(row[0]) for row in rows]

    async def list_chunks_for_document(self, document_id: str) -> list[Chunk]:
        rows = await self._fetch_all(
            "SELECT json FROM chunks WHERE document_id=? ORDER BY rowid",
            (document_id,),
        )
        return [Chunk.model_validate_json(row[0]) for row in rows]

    async def list_chunks_for_project(self, project_id: str | None) -> list[Chunk]:
        rows = await self._fetch_all(
            """
            SELECT c.json
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.project_id IS ?
            ORDER BY c.rowid
            """,
            (project_id,),
        )
        return [Chunk.model_validate_json(row[0]) for row in rows]

    async def get_chunks_by_ids(self, ids: list[str]) -> list[Chunk]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = await self._fetch_all(
            f"SELECT json FROM chunks WHERE id IN ({placeholders})",
            tuple(ids),
        )
        chunks_by_id = {ch.id: ch for ch in (Chunk.model_validate_json(row[0]) for row in rows)}
        return [chunks_by_id[i] for i in ids if i in chunks_by_id]

    async def list_requirements(self, project_id: str | None) -> list[Requirement]:
        rows = await self._fetch_all(
            "SELECT json FROM requirements WHERE project_id IS ? ORDER BY rowid",
            (project_id,),
        )
        return [Requirement.model_validate_json(row[0]) for row in rows]

    async def list_test_plans(self, project_id: str | None) -> list[TestPlan]:
        rows = await self._fetch_all(
            "SELECT json FROM test_plans WHERE project_id IS ? ORDER BY rowid DESC",
            (project_id,),
        )
        return [TestPlan.model_validate_json(row[0]) for row in rows]

    async def get_test_plan(self, plan_id: str) -> TestPlan | None:
        rows = await self._fetch_all("SELECT json FROM test_plans WHERE id=?", (plan_id,))
        if not rows:
            return None
        return TestPlan.model_validate_json(rows[0][0])

    async def update_test_case_status(
        self,
        *,
        project_id: str,
        plan_id: str,
        test_case_id: str,
        status: TestCaseStatus,
        status_note: str | None = None,
    ) -> TestPlan | None:
        plan = await self.get_test_plan(plan_id)
        if plan is None or plan.project_id != project_id:
            return None
        target = next((tc for tc in plan.test_cases if tc.id == test_case_id), None)
        if target is None:
            return None
        target.status = status
        target.status_note = status_note
        await self.save_test_plan(plan)
        return plan

    async def delete_document(self, doc_id: str) -> None:
        await self._db().execute(
            "DELETE FROM requirements WHERE source_document_id=?",
            (doc_id,),
        )
        await self._db().execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        await self._db().execute("DELETE FROM sections WHERE document_id=?", (doc_id,))
        await self._db().execute("DELETE FROM documents WHERE id=?", (doc_id,))
        await self._db().commit()

    async def delete_test_plan(self, plan_id: str) -> None:
        await self._db().execute("DELETE FROM test_cases WHERE plan_id=?", (plan_id,))
        await self._db().execute("DELETE FROM test_plans WHERE id=?", (plan_id,))
        await self._db().commit()

    async def delete_project(self, project_id: str) -> int:
        docs = await self.list_documents(project_id)
        for doc in docs:
            await self.delete_document(doc.id)
        await self._db().execute("DELETE FROM resources WHERE project_id=?", (project_id,))
        await self._db().commit()
        plans = await self.list_test_plans(project_id)
        for plan in plans:
            await self.delete_test_plan(plan.id)
        return len(docs)

    async def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        async with self._db().execute(sql, params) as cur:
            return await cur.fetchall()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def _row_to_pending_chat_action(row: tuple[Any, ...]) -> PendingChatAction:
    (
        action_id,
        session_id,
        user_id,
        project_id,
        action,
        payload,
        created_at,
        expires_at,
        consumed_at,
    ) = row
    return PendingChatAction(
        id=action_id,
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        action=ChatAction(action),
        payload=json.loads(payload),
        created_at=datetime.fromisoformat(created_at),
        expires_at=datetime.fromisoformat(expires_at),
        consumed_at=datetime.fromisoformat(consumed_at) if consumed_at else None,
    )
