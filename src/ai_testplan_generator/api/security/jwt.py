"""JWT encoding and decoding (M13).

Algorithm selection:
  - RS256 when ``settings.jwt_private_key_path`` is set (production).
  - HS256 + ``settings.jwt_secret`` otherwise (local dev only).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt

from ai_testplan_generator.api.errors import AuthError
from ai_testplan_generator.config import Settings


def _algorithm(settings: Settings) -> str:
    return "RS256" if settings.jwt_private_key_path else "HS256"


def _encode_key(settings: Settings) -> str:
    if settings.jwt_private_key_path:
        return Path(settings.jwt_private_key_path).read_text()
    return settings.jwt_secret


def _decode_key(settings: Settings) -> str:
    if settings.jwt_public_key_path:
        return Path(settings.jwt_public_key_path).read_text()
    return settings.jwt_secret


def encode_access_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_access_token_ttl_seconds),
        "jti": f"jwt_{uuid4().hex}",
        "scope": "access",
    }
    return str(jwt.encode(payload, _encode_key(settings), algorithm=_algorithm(settings)))


def encode_refresh_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds),
        "jti": f"jwt_{uuid4().hex}",
        "scope": "refresh",
    }
    return str(jwt.encode(payload, _encode_key(settings), algorithm=_algorithm(settings)))


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return dict(
            jwt.decode(
                token,
                _decode_key(settings),
                algorithms=[_algorithm(settings)],
            )
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Invalid token: {exc}")


def token_expires_at(payload: dict[str, Any]) -> datetime:
    exp = payload.get("exp")
    if isinstance(exp, datetime):
        return exp.astimezone(timezone.utc)
    if isinstance(exp, (int, float)):
        return datetime.fromtimestamp(exp, tz=timezone.utc)
    raise AuthError("Token is missing an expiry.")
