"""Chat / copilot endpoints (M08).

POST /chat                        send one turn -> ChatReply
GET  /chat/{session_id}/history   episodic history for a session
POST /chat/{session_id}/confirm   reject unsupported pending mutations
WS   /chat/{session_id}/stream    WebSocket streaming tokens
"""

from __future__ import annotations

import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ai_testplan_generator.api.deps import (
    get_brain,
    get_current_user,
    get_current_user_ws,
    get_project_repo,
)
from ai_testplan_generator.api.errors import AuthError, UnsupportedFeatureError
from ai_testplan_generator.api.schemas.chat import (
    ChatReply,
    ChatRequest,
    ConfirmRequest,
    HistoryResponse,
)
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.llm.base import ChatMessage
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.pipelines.interactive import InteractivePipeline

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])

# Module-level pipeline cache — keeps sessions alive across requests.
_pipelines: dict[str, InteractivePipeline] = {}


def _get_pipeline(brain: Brain) -> InteractivePipeline:
    key = str(id(brain))
    if key not in _pipelines:
        _pipelines[key] = InteractivePipeline(brain)
    return _pipelines[key]


async def _ensure_project_chat_access(
    project_id: str | None,
    current_user: User,
    project_repo: ProjectRepository,
) -> None:
    if not project_id or current_user.is_admin:
        return
    member = await project_repo.get_member(project_id, current_user.id)
    if member is not None:
        return
    project = await project_repo.get_project(project_id)
    if project is not None and project.owner_id == current_user.id:
        return
    raise AuthError(f"Forbidden: not a member of project '{project_id}'.")


@router.post("/chat", response_model=ChatReply, summary="Send a chat message")
async def chat(
    body: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    brain: Annotated[Brain, Depends(get_brain)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ChatReply:
    await _ensure_project_chat_access(body.project_id, current_user, project_repo)
    pipeline = _get_pipeline(brain)
    session = pipeline.session(project_id=body.project_id, session_id=body.session_id)
    reply = await session.ask(body.message)
    return ChatReply(
        session_id=session.session_id,
        assistant_message=reply.assistant_message,
        pending_action=reply.pending_action,
        unsupported_action=reply.unsupported_action,
    )


@router.get(
    "/chat/{session_id}/history",
    response_model=HistoryResponse,
    summary="Retrieve episodic history for a session",
)
async def chat_history(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    brain: Annotated[Brain, Depends(get_brain)],
    limit: int = 50,
) -> HistoryResponse:
    events = await brain.memory.episodic.recent(session_id, limit=limit)
    return HistoryResponse.from_events(session_id, events)


@router.post(
    "/chat/{session_id}/confirm",
    response_model=ChatReply,
    summary="Confirm or discard a pending copilot action",
)
async def confirm_action(
    session_id: str,  # noqa: ARG001
    body: ConfirmRequest,  # noqa: ARG001
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> ChatReply:
    raise UnsupportedFeatureError(
        "Chat-confirmed plan mutations are outside the current product scope. "
        "Use the interactive generation checkpoints to revise persisted plans."
    )


@router.websocket("/chat/{session_id}/stream")
async def chat_stream(
    session_id: str,
    websocket: WebSocket,
    brain: Annotated[Brain, Depends(get_brain)],
) -> None:
    """WebSocket endpoint for streaming token-by-token responses.

    Loads recent episodic history before each turn so the assistant can
    reference earlier user/assistant messages in the same session.
    """
    try:
        current_user = await get_current_user_ws(websocket)
    except AuthError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    websocket.state.current_user = current_user
    try:
        while True:
            message = await websocket.receive_text()

            # Build prompt: prior turns from episodic memory + current message.
            # Cap at 20 message events to keep token usage bounded.
            history = await brain.memory.episodic.recent(
                session_id, limit=20, kinds=["message"]
            )
            messages: list[ChatMessage] = []
            for ev in history:
                role = "user" if ev.actor == "user" else "assistant"
                messages.append(ChatMessage(role=role, content=ev.content))
            messages.append(ChatMessage(role="user", content=message))

            full_text: list[str] = []
            async for token in brain.llm.stream(messages, role="balanced"):
                full_text.append(token)
                await websocket.send_text(json.dumps({"token": token}))
            await brain.memory.log_event(session_id, "user", "message", message)
            await brain.memory.log_event(
                session_id, "assistant", "message", "".join(full_text)
            )
            await websocket.send_text(json.dumps({"done": True}))
    except WebSocketDisconnect:
        _log.info("ws_disconnected", session_id=session_id)
    except Exception as exc:
        _log.error("ws_error", session_id=session_id, error=str(exc))
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
