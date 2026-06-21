"""Auth-related data classes (M12).

Lightweight data containers only — no business logic. Business logic
(hashing, token encoding, key verification) lives in api/security/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class ApiKey:
    id: str = field(default_factory=lambda: f"key_{uuid4().hex[:10]}")
    user_id: str = ""
    name: str = ""
    hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


@dataclass
class ProviderApiKey:
    id: str = field(default_factory=lambda: f"pkey_{uuid4().hex[:10]}")
    user_id: str = ""
    provider: str = ""
    label: str = ""
    encrypted_api_key: str = ""
    key_tail: str = ""
    is_enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
