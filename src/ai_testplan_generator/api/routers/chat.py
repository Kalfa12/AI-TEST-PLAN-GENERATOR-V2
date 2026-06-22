"""Chat / copilot endpoints (M08).

POST /chat                        send one turn -> ChatReply
GET  /chat/{session_id}/history   episodic history for a session
POST /chat/{session_id}/confirm   reject unsupported pending mutations
WS   /chat/{session_id}/stream    compatibility stream backed by CopilotAgent
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
from ai_testplan_generator.api.errors import AuthError, NotFoundError, UnsupportedFeatureError
from ai_testplan_generator.api.errors import ValidationError as ApiValidationError
from ai_testplan_generator.api.schemas.chat import (
    ChatContextResponse,
    ChatPlanContext,
    ChatReply,
    ChatRequest,
    ConfirmRequest,
    HistoryResponse,
)
from ai_testplan_generator.domain.chat_actions import apply_pending_chat_action
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.domain.users import User
from ai_testplan_generator.api.security.projects import ensure_project_access
from ai_testplan_generator.models import TestPlan
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
    if project_id is None and current_user.is_admin:
        return
    await ensure_project_access(
        project_id=project_id,
        current_user=current_user,
        project_repo=project_repo,
    )


def _summarise_plan_context(plan: TestPlan) -> ChatPlanContext:
    total = len(plan.coverage_matrix)
    covered = sum(1 for case_ids in plan.coverage_matrix.values() if case_ids)
    if total == 0:
        linked_requirement_ids = {
            req_id for tc in plan.test_cases for req_id in tc.requirement_ids
        }
        total = len(linked_requirement_ids)
        covered = total
    coverage_percent = round((covered / total) * 100) if total else 0
    return ChatPlanContext(
        id=plan.id,
        title=plan.title,
        n_test_cases=len(plan.test_cases),
        covered_requirements=covered,
        total_requirements=total,
        coverage_percent=coverage_percent,
    )


@router.post("/chat", response_model=ChatReply, summary="Send a chat message")
async def chat(
    body: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    brain: Annotated[Brain, Depends(get_brain)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ChatReply:
    await _ensure_project_chat_access(body.project_id, current_user, project_repo)
    pipeline = _get_pipeline(brain)
    session = pipeline.session(
        project_id=body.project_id,
        session_id=body.session_id,
        user_id=current_user.id,
    )
    reply = await session.ask(body.message)
    return ChatReply(
        session_id=session.session_id,
        assistant_message=reply.assistant_message,
        pending_action=reply.pending_action,
        pending_action_id=reply.pending_action_id,
        pending_action_preview=reply.pending_action_preview,
        unsupported_action=reply.unsupported_action,
    )


@router.get(
    "/chat/context",
    response_model=ChatContextResponse,
    summary="Show the project context available to chat",
)
async def chat_context(
    project_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    brain: Annotated[Brain, Depends(get_brain)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ChatContextResponse:
    await _ensure_project_chat_access(project_id, current_user, project_repo)
    project = await project_repo.get_project(project_id)
    if project is None:
        raise NotFoundError(f"Project '{project_id}' not found.")

    documents = await brain.memory.get_documents_for_project(project_id)
    requirements = await brain.memory.get_requirements_for_project(project_id)
    plans = await brain.memory.get_test_plans_for_project(project_id)

    return ChatContextResponse(
        project_id=project.id,
        project_name=project.name,
        industry=project.industry.value,
        documents=len(documents),
        requirements=len(requirements),
        plans=len(plans),
        latest_plan=_summarise_plan_context(plans[0]) if plans else None,
    )


@router.get(
    "/chat/{session_id}/history",
    response_model=HistoryResponse,
    summary="Retrieve episodic history for a session",
)
async def chat_history(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    brain: Annotated[Brain, Depends(get_brain)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
    project_id: str | None = None,
    limit: int = 50,
) -> HistoryResponse:
    if project_id is None and not current_user.is_admin:
        raise AuthError("Forbidden: project_id is required to read chat history.")
    if project_id is not None:
        await _ensure_project_chat_access(project_id, current_user, project_repo)
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
    current_user: Annotated[User, Depends(get_current_user)],
    brain: Annotated[Brain, Depends(get_brain)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repo)],
) -> ChatReply:
    repo = brain.memory.artifact_repo
    if repo is None:
        raise UnsupportedFeatureError("Chat mutations require durable artifact storage.")
    pending = await repo.get_pending_chat_action(
        session_id=session_id,
        user_id=current_user.id,
        action_id=body.action_id,
    )
    if pending is None:
        raise ApiValidationError("No active pending action for this chat session.")

    await _ensure_project_chat_access(pending.project_id, current_user, project_repo)

    if not body.confirmed:
        await repo.consume_pending_chat_action(pending.id)
        await repo.record_audit_event(
            user_id=current_user.id,
            project_id=pending.project_id,
            action=f"CHAT_DISCARD:{pending.action.value}",
            target_type="PendingChatAction",
            target_id=pending.id,
            metadata={"session_id": session_id},
        )
        return ChatReply(
            session_id=session_id,
            assistant_message=f"Discarded pending action {pending.action.value}.",
            pending_action=None,
        )

    try:
        result = await apply_pending_chat_action(repo, pending)
    except ValueError as exc:
        raise ApiValidationError(str(exc)) from exc

    await repo.consume_pending_chat_action(pending.id)
    await brain.memory.hydrate()
    await repo.record_audit_event(
        user_id=current_user.id,
        project_id=pending.project_id,
        action=f"CHAT_CONFIRM:{pending.action.value}",
        target_type="TestPlan",
        target_id=result.plan_id,
        metadata={
            "session_id": session_id,
            "action_id": pending.id,
            "before_test_case_ids": result.before_test_case_ids,
            "after_test_case_ids": result.after_test_case_ids,
            "affected_test_case_ids": result.affected_test_case_ids,
        },
    )
    await brain.memory.log_event(
        session_id,
        actor="copilot",
        kind="mutation_applied",
        content=result.message,
        action_id=pending.id,
        plan_id=result.plan_id,
    )
    return ChatReply(
        session_id=session_id,
        assistant_message=result.message,
        pending_action=None,
    )


@router.websocket("/chat/{session_id}/stream")
async def chat_stream(
    session_id: str,
    websocket: WebSocket,
    brain: Annotated[Brain, Depends(get_brain)],
) -> None:
    """WebSocket endpoint backed by the same CopilotAgent path as POST /chat.

    The UI now uses POST /chat for context-rich replies and pending action
    metadata. This compatibility endpoint returns the full assistant message as
    one token-like payload so older callers still get grounded Copilot answers.
    """
    try:
        current_user = await get_current_user_ws(websocket)
    except AuthError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    websocket.state.current_user = current_user
    project_id = websocket.query_params.get("project_id")
    context_keys: list[str] = []
    try:
        import structlog.contextvars as sc_ctx

        values = {"session_id": session_id}
        if project_id:
            values["project_id"] = project_id
        sc_ctx.bind_contextvars(**values)
        context_keys = list(values)
    except Exception:  # noqa: BLE001
        context_keys = []

    try:
        await _ensure_project_chat_access(
            project_id, current_user, websocket.app.state.project_repo
        )
        pipeline = _get_pipeline(brain)
        session = pipeline.session(
            project_id=project_id,
            session_id=session_id,
            user_id=current_user.id,
        )
        while True:
            message = await websocket.receive_text()
            reply = await session.ask(message)
            await websocket.send_text(json.dumps({"token": reply.assistant_message}))
            await websocket.send_text(
                json.dumps(
                    {
                        "done": True,
                        "pending_action": reply.pending_action,
                        "pending_action_id": reply.pending_action_id,
                        "pending_action_preview": reply.pending_action_preview,
                        "unsupported_action": reply.unsupported_action,
                    }
                )
            )
    except WebSocketDisconnect:
        _log.info("ws_disconnected", session_id=session_id)
    except Exception as exc:
        _log.error("ws_error", session_id=session_id, error=str(exc))
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        if context_keys:
            try:
                import structlog.contextvars as sc_ctx

                sc_ctx.unbind_contextvars(*context_keys)
            except Exception:
                pass
