"""User identity model and async SQLite repository (M12).

M10 planted the minimal User dataclass. M12 extends it with password_hash
and a full UserRepository backed by the same app SQLite database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
import structlog

from ai_testplan_generator.domain.auth import ApiKey

_log = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL,
    password_hash   TEXT,
    created_at      TEXT NOT NULL,
    disabled_at     TEXT,
    is_admin        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS api_keys (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,
    hash            TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    revoked_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
"""


@dataclass
class User:
    id: str = field(default_factory=lambda: f"usr_{uuid4().hex[:10]}")
    email: str = ""
    display_name: str = ""
    password_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disabled_at: datetime | None = None
    is_admin: bool = False

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None


class UserRepository:
    """Async SQLite-backed CRUD for users and API keys."""

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, *, db_path: str) -> "UserRepository":
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
        await self._ensure_schema()
        await self._conn.commit()
        _log.info("user_repo_init", db_path=path_str)

    async def _ensure_schema(self) -> None:
        """Apply lightweight migrations for repositories created by older builds."""
        async with self._db().execute("PRAGMA table_info(users)") as cur:
            columns = {str(row[1]) for row in await cur.fetchall()}
        if "is_admin" not in columns:
            await self._db().execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("UserRepository not initialised — call create() first")
        return self._conn

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str | None = None,
        is_admin: bool = False,
    ) -> User:
        user = User(
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            is_admin=is_admin,
        )
        await self._db().execute(
            "INSERT INTO users (id, email, display_name, password_hash, created_at, is_admin)"
            " VALUES (?,?,?,?,?,?)",
            (user.id, user.email, user.display_name, user.password_hash,
             user.created_at.isoformat(), int(user.is_admin)),
        )
        await self._db().commit()
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        async with self._db().execute(
            "SELECT id,email,display_name,password_hash,created_at,disabled_at,is_admin"
            " FROM users WHERE id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        async with self._db().execute(
            "SELECT id,email,display_name,password_hash,created_at,disabled_at,is_admin"
            " FROM users WHERE email=?",
            (email,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def disable_user(self, user_id: str) -> bool:
        ts = datetime.now(timezone.utc).isoformat()
        async with self._db().execute(
            "UPDATE users SET disabled_at=? WHERE id=? AND disabled_at IS NULL",
            (ts, user_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        return changed > 0

    # ------------------------------------------------------------------
    # API Keys
    # ------------------------------------------------------------------

    async def create_api_key(
        self,
        *,
        user_id: str,
        name: str,
        key_hash: str,
    ) -> ApiKey:
        key = ApiKey(user_id=user_id, name=name, hash=key_hash)
        await self._db().execute(
            "INSERT INTO api_keys (id, user_id, name, hash, created_at)"
            " VALUES (?,?,?,?,?)",
            (key.id, key.user_id, key.name, key.hash, key.created_at.isoformat()),
        )
        await self._db().commit()
        return key

    async def get_api_keys(self, user_id: str) -> list[ApiKey]:
        async with self._db().execute(
            "SELECT id,user_id,name,hash,created_at,last_used_at,revoked_at"
            " FROM api_keys WHERE user_id=?",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_api_key(r) for r in rows]

    async def get_api_key_by_id(self, key_id: str) -> ApiKey | None:
        async with self._db().execute(
            "SELECT id,user_id,name,hash,created_at,last_used_at,revoked_at"
            " FROM api_keys WHERE id=?",
            (key_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_api_key(row) if row else None

    async def revoke_api_key(self, key_id: str) -> bool:
        ts = datetime.now(timezone.utc).isoformat()
        async with self._db().execute(
            "UPDATE api_keys SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (ts, key_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        return changed > 0

    async def touch_api_key(self, key_id: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        await self._db().execute(
            "UPDATE api_keys SET last_used_at=? WHERE id=?",
            (ts, key_id),
        )
        await self._db().commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


# ------------------------------------------------------------------
# Row mappers
# ------------------------------------------------------------------

def _row_to_user(row: Any) -> User:
    uid, email, display_name, password_hash, created_at, disabled_at, is_admin = row
    return User(
        id=uid,
        email=email,
        display_name=display_name,
        password_hash=password_hash,
        created_at=datetime.fromisoformat(created_at),
        disabled_at=datetime.fromisoformat(disabled_at) if disabled_at else None,
        is_admin=bool(is_admin),
    )


def _row_to_api_key(row: Any) -> ApiKey:
    kid, user_id, name, hash_, created_at, last_used_at, revoked_at = row
    return ApiKey(
        id=kid,
        user_id=user_id,
        name=name,
        hash=hash_,
        created_at=datetime.fromisoformat(created_at),
        last_used_at=datetime.fromisoformat(last_used_at) if last_used_at else None,
        revoked_at=datetime.fromisoformat(revoked_at) if revoked_at else None,
    )
