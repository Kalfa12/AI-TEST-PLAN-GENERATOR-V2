"""Request/response schemas for the auth router (M13)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
    access_token: str | None = None


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None


class ApiKeyCreatedResponse(BaseModel):
    id: str
    name: str
    key: str
    created_at: str


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str
    is_active: bool
    is_admin: bool = False
