"""User identity model and async SQLite repository (M12).

M10 planted the minimal User dataclass. M12 extends it with password_hash
and a full UserRepository backed by the same app SQLite database.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
import structlog
from cryptography.fernet import Fernet

from ai_testplan_generator.domain.auth import ApiKey, ProviderApiKey

_log = structlog.get_logger(__name__)

_SQLITE_BUSY_TIMEOUT_MS = 30_000

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

CREATE TABLE IF NOT EXISTS token_revocations (
    jti             TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    scope           TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    revoked_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_token_revocations_user ON token_revocations(user_id);
CREATE INDEX IF NOT EXISTS idx_token_revocations_expires ON token_revocations(expires_at);

CREATE TABLE IF NOT EXISTS provider_keys (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(id),
    provider            TEXT NOT NULL,
    label               TEXT NOT NULL,
    encrypted_api_key   TEXT NOT NULL,
    key_tail            TEXT NOT NULL,
    is_enabled          INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    last_used_at        TEXT,
    revoked_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_provider_keys_user_provider ON provider_keys(user_id, provider);
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

    def __init__(self, *, db_path: str, encryption_secret: str | None = None) -> None:
        self._db_path = db_path
        self._encryption_secret = encryption_secret or "ai-testplan-generator-provider-keys"
        self._conn: aiosqlite.Connection | None = None
        self._fernet = _build_fernet(self._encryption_secret)

    @classmethod
    async def create(cls, *, db_path: str, encryption_secret: str | None = None) -> "UserRepository":
        repo = cls(db_path=db_path, encryption_secret=encryption_secret)
        await repo._init()
        return repo

    async def _init(self) -> None:
        path_str = self._db_path
        if path_str != ":memory:":
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(path_str, timeout=30.0)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
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
        await self._db().execute(
            """
            CREATE TABLE IF NOT EXISTS token_revocations (
                jti             TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                scope           TEXT NOT NULL,
                expires_at      TEXT NOT NULL,
                revoked_at      TEXT NOT NULL
            )
            """
        )
        await self._db().execute(
            "CREATE INDEX IF NOT EXISTS idx_token_revocations_user "
            "ON token_revocations(user_id)"
        )
        await self._db().execute(
            "CREATE INDEX IF NOT EXISTS idx_token_revocations_expires "
            "ON token_revocations(expires_at)"
        )
        await self._db().execute(
            """
            CREATE TABLE IF NOT EXISTS provider_keys (
                id                  TEXT PRIMARY KEY,
                user_id             TEXT NOT NULL REFERENCES users(id),
                provider            TEXT NOT NULL,
                label               TEXT NOT NULL,
                encrypted_api_key   TEXT NOT NULL,
                key_tail            TEXT NOT NULL,
                is_enabled          INTEGER NOT NULL DEFAULT 1,
                created_at          TEXT NOT NULL,
                last_used_at        TEXT,
                revoked_at          TEXT
            )
            """
        )
        await self._db().execute(
            "CREATE INDEX IF NOT EXISTS idx_provider_keys_user_provider "
            "ON provider_keys(user_id, provider)"
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

    async def update_user(
        self,
        user_id: str,
        *,
        email: str,
        display_name: str,
    ) -> User | None:
        ts = datetime.now(timezone.utc).isoformat()
        async with self._db().execute(
            "UPDATE users SET email=?, display_name=? WHERE id=? AND disabled_at IS NULL",
            (email, display_name, user_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        if changed == 0:
            return None
        return await self.get_by_id(user_id)

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

    # ------------------------------------------------------------------
    # JWT token revocation
    # ------------------------------------------------------------------

    async def revoke_token(
        self,
        *,
        jti: str,
        user_id: str,
        scope: str,
        expires_at: datetime,
    ) -> None:
        await self.purge_expired_token_revocations()
        await self._db().execute(
            """
            INSERT OR REPLACE INTO token_revocations
                (jti, user_id, scope, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                jti,
                user_id,
                scope,
                expires_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self._db().commit()

    async def is_token_revoked(self, jti: str) -> bool:
        await self.purge_expired_token_revocations()
        async with self._db().execute(
            "SELECT 1 FROM token_revocations WHERE jti=? LIMIT 1",
            (jti,),
        ) as cur:
            return await cur.fetchone() is not None

    async def purge_expired_token_revocations(self) -> None:
        await self._db().execute(
            "DELETE FROM token_revocations WHERE expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        await self._db().commit()

    # ------------------------------------------------------------------
    # Provider API keys
    # ------------------------------------------------------------------

    async def create_provider_key(
        self,
        *,
        user_id: str,
        provider: str,
        label: str,
        api_key: str,
        is_enabled: bool = True,
    ) -> ProviderApiKey:
        provider_key = ProviderApiKey(
            user_id=user_id,
            provider=provider.strip().lower(),
            label=label.strip(),
            encrypted_api_key=self._encrypt(api_key),
            key_tail=api_key[-4:] if len(api_key) >= 4 else api_key,
            is_enabled=is_enabled,
        )
        await self._db().execute(
            "INSERT INTO provider_keys (id, user_id, provider, label, encrypted_api_key, key_tail,"
            " is_enabled, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                provider_key.id,
                provider_key.user_id,
                provider_key.provider,
                provider_key.label,
                provider_key.encrypted_api_key,
                provider_key.key_tail,
                1 if provider_key.is_enabled else 0,
                provider_key.created_at.isoformat(),
            ),
        )
        if is_enabled:
            await self._disable_other_provider_keys(
                user_id=user_id,
                provider=provider_key.provider,
                keep_id=provider_key.id,
            )
        await self._db().commit()
        return provider_key

    async def get_provider_keys(self, user_id: str) -> list[ProviderApiKey]:
        async with self._db().execute(
            "SELECT id,user_id,provider,label,encrypted_api_key,key_tail,is_enabled,created_at,"
            "last_used_at,revoked_at FROM provider_keys WHERE user_id=? ORDER BY provider,label,created_at",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_provider_key(r) for r in rows]

    async def get_provider_key_by_id(self, key_id: str) -> ProviderApiKey | None:
        async with self._db().execute(
            "SELECT id,user_id,provider,label,encrypted_api_key,key_tail,is_enabled,created_at,"
            "last_used_at,revoked_at FROM provider_keys WHERE id=?",
            (key_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_provider_key(row) if row else None

    async def update_provider_key(
        self,
        key_id: str,
        *,
        label: str | None = None,
        is_enabled: bool | None = None,
    ) -> ProviderApiKey | None:
        current = await self.get_provider_key_by_id(key_id)
        if current is None:
            return None
        new_label = label.strip() if label is not None else current.label
        new_enabled = current.is_enabled if is_enabled is None else is_enabled
        await self._db().execute(
            "UPDATE provider_keys SET label=?, is_enabled=? WHERE id=?",
            (new_label, 1 if new_enabled else 0, key_id),
        )
        if new_enabled:
            await self._disable_other_provider_keys(
                user_id=current.user_id,
                provider=current.provider,
                keep_id=key_id,
            )
        await self._db().commit()
        return await self.get_provider_key_by_id(key_id)

    async def revoke_provider_key(self, key_id: str) -> bool:
        ts = datetime.now(timezone.utc).isoformat()
        async with self._db().execute(
            "UPDATE provider_keys SET revoked_at=?, is_enabled=0 WHERE id=? AND revoked_at IS NULL",
            (ts, key_id),
        ) as cur:
            changed = cur.rowcount
        await self._db().commit()
        return changed > 0

    async def _disable_other_provider_keys(self, *, user_id: str, provider: str, keep_id: str) -> None:
        await self._db().execute(
            "UPDATE provider_keys SET is_enabled=0 WHERE user_id=? AND provider=? AND id<>? AND revoked_at IS NULL",
            (user_id, provider, keep_id),
        )

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

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


def _row_to_provider_key(row: Any) -> ProviderApiKey:
    (
        pid,
        user_id,
        provider,
        label,
        encrypted_api_key,
        key_tail,
        is_enabled,
        created_at,
        last_used_at,
        revoked_at,
    ) = row
    return ProviderApiKey(
        id=pid,
        user_id=user_id,
        provider=provider,
        label=label,
        encrypted_api_key=encrypted_api_key,
        key_tail=key_tail,
        is_enabled=bool(is_enabled),
        created_at=datetime.fromisoformat(created_at),
        last_used_at=datetime.fromisoformat(last_used_at) if last_used_at else None,
        revoked_at=datetime.fromisoformat(revoked_at) if revoked_at else None,
    )


def _build_fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
