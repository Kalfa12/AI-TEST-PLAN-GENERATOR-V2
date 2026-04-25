"""API key generation and verification (M13).

Raw key format presented to the caller: ``{key_id}.{raw_material}``
  - key_id     — the database row id (key_<hex>), used for O(1) lookup
  - raw_material — 32 random bytes, base64url-encoded (no padding, 43 chars)

Only the bcrypt hash of raw_material is stored in the database.  The
raw_material is always 43 chars — well within bcrypt's 72-byte limit.
"""

from __future__ import annotations

import base64
import secrets

import bcrypt


def generate_api_key() -> tuple[str, str]:
    """Return ``(raw_material, hashed_material)``.

    The caller must prefix raw_material with the DB key_id to produce the
    final key shown to the user.
    """
    raw_bytes = secrets.token_bytes(32)
    raw_material = base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(raw_material.encode(), salt).decode()
    return raw_material, hashed


def verify_api_key(raw_material: str, hashed: str) -> bool:
    return bool(bcrypt.checkpw(raw_material.encode(), hashed.encode()))


def build_full_key(key_id: str, raw_material: str) -> str:
    """Combine key_id and raw_material into the string returned to callers."""
    return f"{key_id}.{raw_material}"


def parse_full_key(full_key: str) -> tuple[str, str] | None:
    """Split a full API key into ``(key_id, raw_material)``.

    Returns None if the format is invalid.
    """
    parts = full_key.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]
