"""FastAPI dependency injection helpers.

All dependencies read from request.app.state, which is populated
during the lifespan in api/app.py.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request, WebSocket

from ai_testplan_generator.api.errors import AuthError
from ai_testplan_generator.api.jobs import Job
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.jobs import JobRepository
from ai_testplan_generator.domain.users import User, UserRepository
from ai_testplan_generator.events.broker import EventBroker
from ai_testplan_generator.jobs.queue import JobQueueProtocol
from ai_testplan_generator.models import DefectReport, TestPlan
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore

def get_brain(request: Request = None, websocket: WebSocket = None) -> Brain:
    conn = request if request else websocket
    return cast(Brain, conn.app.state.brain)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_blob_store(request: Request) -> BlobStore:
    return cast(BlobStore, request.app.state.blob_store)


def get_project_repo(request: Request) -> ProjectRepository:
    return cast(ProjectRepository, request.app.state.project_repo)


def get_event_broker(request: Request) -> EventBroker:
    return cast(EventBroker, request.app.state.event_broker)


def get_job_queue(request: Request) -> JobQueueProtocol:
    return cast(JobQueueProtocol, request.app.state.job_queue)


def get_job_repo(request: Request) -> JobRepository:
    return cast(JobRepository, request.app.state.job_repo)


def get_jobs(request: Request) -> dict[str, Job]:
    return cast(dict[str, Job], request.app.state.jobs)


def get_plans(request: Request) -> dict[str, TestPlan]:
    return cast(dict[str, TestPlan], request.app.state.plans)


def get_project_plans(request: Request) -> dict[str, list[str]]:
    return cast(dict[str, list[str]], request.app.state.project_plans)


def get_defects(request: Request) -> dict[str, DefectReport]:
    return cast(dict[str, DefectReport], request.app.state.defects)


def get_user_repo(request: Request) -> UserRepository:
    return cast(UserRepository, request.app.state.user_repo)


async def get_current_user(
    request: Request,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Resolve the authenticated caller from a Bearer JWT or X-Api-Key header."""
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-Api-Key", "")
    query_token = request.query_params.get("token", "")

    if auth_header.startswith("Bearer ") or query_token:
        token = auth_header[7:] if auth_header.startswith("Bearer ") else query_token
        from ai_testplan_generator.api.security.jwt import decode_token

        payload = decode_token(token, settings)
        user_id = str(payload.get("sub", ""))
        if payload.get("scope") != "access":
            raise AuthError("Token is not an access token.")
        user = await user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthError("User not found or disabled.")
        request.state.current_user = user
        return user

    if api_key_header:
        from ai_testplan_generator.api.security.api_key import (
            parse_full_key,
            verify_api_key,
        )

        parsed = parse_full_key(api_key_header)
        if parsed is None:
            raise AuthError("Malformed API key.")
        key_id, raw_material = parsed
        db_key = await user_repo.get_api_key_by_id(key_id)
        if db_key is None or db_key.is_revoked:
            raise AuthError("Invalid or revoked API key.")
        if not verify_api_key(raw_material, db_key.hash):
            raise AuthError("Invalid API key.")
        user = await user_repo.get_by_id(db_key.user_id)
        if user is None or not user.is_active:
            raise AuthError("User not found or disabled.")
        # Fire-and-forget last_used_at update.
        import asyncio

        asyncio.create_task(user_repo.touch_api_key(key_id))
        request.state.current_user = user
        return user

    raise AuthError("Authentication required.")


async def get_current_user_ws(websocket: WebSocket) -> User:
    """Resolve a WebSocket caller from a JWT token query parameter."""
    settings = cast(Settings, websocket.app.state.settings)
    user_repo = cast(UserRepository, websocket.app.state.user_repo)
    token = websocket.query_params.get("token", "")
    if not token:
        raise AuthError("Authentication required.")

    from ai_testplan_generator.api.security.jwt import decode_token

    payload = decode_token(token, settings)
    user_id = str(payload.get("sub", ""))
    if payload.get("scope") != "access":
        raise AuthError("Token is not an access token.")
    user = await user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or disabled.")
    return user
