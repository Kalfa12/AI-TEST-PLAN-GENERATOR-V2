"""Chat / copilot endpoints (M08).

POST /chat                        send one turn → ChatReply
GET  /chat/{session_id}/history   episodic history for a session
POST /chat/{session_id}/confirm   confirm a pending mutation
WS   /chat/{session_id}/stream    WebSocket streaming tokens
"""

from __future__ import annotations

import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ai_testplan_generator.api.deps import get_brain
from ai_testplan_generator.api.schemas.chat import (
    ChatReply,
    ChatRequest,
    ConfirmRequest,
    HistoryResponse,
)
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


@router.post("/chat", response_model=ChatReply, summary="Send a chat message")
async def chat(
    body: ChatRequest,
    brain: Annotated[Brain, Depends(get_brain)],
) -> ChatReply:
    pipeline = _get_pipeline(brain)
    session = pipeline.session(project_id=body.project_id, session_id=body.session_id)
    reply = await session.ask(body.message)
    return ChatReply(
        session_id=session.session_id,
        assistant_message=reply.assistant_message,
        pending_action=reply.pending_action,
    )


@router.get(
    "/chat/{session_id}/history",
    response_model=HistoryResponse,
    summary="Retrieve episodic history for a session",
)
async def chat_history(
    session_id: str,
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
    session_id: str,
    body: ConfirmRequest,
    brain: Annotated[Brain, Depends(get_brain)],
) -> ChatReply:
    message = "Confirmed." if body.confirmed else "Discarded."
    pipeline = _get_pipeline(brain)
    reply = await pipeline.ask(message, session_id=session_id)
    return ChatReply(
        session_id=session_id,
        assistant_message=reply.assistant_message,
        pending_action=reply.pending_action,
    )


@router.websocket("/chat/{session_id}/stream")
async def chat_stream(
    session_id: str,
    websocket: WebSocket,
    brain: Annotated[Brain, Depends(get_brain)],
) -> None:
    """WebSocket endpoint for streaming token-by-token responses."""
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            full_text: list[str] = []
            async for token in brain.llm.stream(
                [ChatMessage(role="user", content=message)],
                role="balanced",
            ):
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
