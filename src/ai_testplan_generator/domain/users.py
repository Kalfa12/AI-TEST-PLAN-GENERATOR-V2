"""Minimal user identity model.

Full auth (passwords, JWT, API keys) is implemented in M12/M13.
This module only provides the data shape used by the project layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class User:
    id: str = field(default_factory=lambda: f"usr_{uuid4().hex[:10]}")
    email: str = ""
    display_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disabled_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None
