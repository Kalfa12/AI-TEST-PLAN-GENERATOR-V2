"""Authentication endpoints (M13).

POST   /auth/login              email + password → access + refresh tokens
POST   /auth/refresh            refresh token → new access token
POST   /auth/logout             revoke refresh token (client-side invalidation)
POST   /auth/api-keys           create API key for the current user
GET    /auth/api-keys           list API keys for the current user
DELETE /auth/api-keys/{id}      revoke an API key
GET    /auth/me                 current user profile
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends

from ai_testplan_generator.api.deps import get_current_user, get_settings, get_user_repo
from ai_testplan_generator.api.errors import AuthError, NotFoundError
from ai_testplan_generator.api.schemas.auth import (
    AccessTokenResponse,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from ai_testplan_generator.api.security.api_key import (
    build_full_key,
    generate_api_key,
)
from ai_testplan_generator.api.security.jwt import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
from ai_testplan_generator.api.security.password import verify_password
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.users import User, UserRepository

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Login / token endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse, summary="Log in with email and password")
async def login(
    body: LoginRequest,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = await user_repo.get_by_email(body.email)
    if user is None or user.password_hash is None:
        raise AuthError("Invalid credentials.")
    if not user.is_active:
        raise AuthError("Account is disabled.")
    if not verify_password(body.password, user.password_hash):
        raise AuthError("Invalid credentials.")

    access_token = encode_access_token(user.id, settings)
    refresh_token = encode_refresh_token(user.id, settings)
    _log.info("auth_login", user_id=user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse, summary="Refresh access token")
async def refresh(
    body: RefreshRequest,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccessTokenResponse:
    payload = decode_token(body.refresh_token, settings)
    if payload.get("scope") != "refresh":
        raise AuthError("Token is not a refresh token.")
    user_id = str(payload.get("sub", ""))
    user = await user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or disabled.")
    return AccessTokenResponse(access_token=encode_access_token(user_id, settings))


@router.post("/logout", status_code=204, summary="Logout (client-side token invalidation)")
async def logout() -> None:
    # Stateless JWTs are invalidated client-side. A production system would
    # maintain a token revocation list (e.g., Redis TTL store) here.
    pass


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

@router.post(
    "/api-keys",
    status_code=201,
    response_model=ApiKeyCreatedResponse,
    summary="Create an API key",
)
async def create_api_key(
    body: CreateApiKeyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> ApiKeyCreatedResponse:
    raw_material, key_hash = generate_api_key()
    api_key = await user_repo.create_api_key(
        user_id=current_user.id, name=body.name, key_hash=key_hash
    )
    full_key = build_full_key(api_key.id, raw_material)
    _log.info("api_key_created", user_id=current_user.id, key_id=api_key.id)
    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key=full_key,
        created_at=api_key.created_at.isoformat(),
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse], summary="List API keys")
async def list_api_keys(
    current_user: Annotated[User, Depends(get_current_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> list[ApiKeyResponse]:
    keys = await user_repo.get_api_keys(current_user.id)
    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            created_at=k.created_at.isoformat(),
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            revoked_at=k.revoked_at.isoformat() if k.revoked_at else None,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204, summary="Revoke an API key")
async def revoke_api_key(
    key_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> None:
    key = await user_repo.get_api_key_by_id(key_id)
    if key is None or key.user_id != current_user.id:
        raise NotFoundError(f"API key '{key_id}' not found.")
    revoked = await user_repo.revoke_api_key(key_id)
    if not revoked:
        raise NotFoundError(f"API key '{key_id}' is already revoked.")
    _log.info("api_key_revoked", user_id=current_user.id, key_id=key_id)


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse, summary="Current user profile")
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        created_at=current_user.created_at.isoformat(),
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
    )
