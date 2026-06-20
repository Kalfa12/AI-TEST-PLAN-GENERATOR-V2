"""Interactive LangGraph.

A lean graph for the chat/copilot mode. One turn = one pass through the
graph. The heavy lifting lives inside `CopilotAgent`; the graph gives us
a stable integration surface (checkpointing, interrupts, streaming) and
a natural seam to later add a confirmation node for mutating actions.

Topology:
    START -> copilot -> maybe_apply -> END

`maybe_apply` is intentionally non-mutating for the current MVP scope. If
the LLM proposes a mutation anyway, the graph turns it into an explicit
unsupported action instead of surfacing a fake confirmation flow.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from langgraph.graph import END, StateGraph

from ai_testplan_generator.agents import CopilotAgent, InteractiveState
from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.domain.chat_actions import (
    ChatAction,
    MUTATING_ACTIONS,
    PendingChatAction,
    action_preview,
    validate_action_payload,
)

SUPPORTED_MUTATING_ACTIONS = {action.value for action in MUTATING_ACTIONS}


def build_interactive_graph(ctx: AgentContext) -> Any:
    copilot = CopilotAgent(ctx)
    graph: StateGraph = StateGraph(InteractiveState)

    async def _copilot(state: InteractiveState) -> dict[str, Any]:
        reply = await copilot.invoke(
            CopilotAgent.Input(user_message=state.user_message)
        )
        proposed_action = (
            reply.proposed_action
            if reply.needs_confirmation and reply.proposed_action != "none"
            else None
        )
        if proposed_action and proposed_action not in SUPPORTED_MUTATING_ACTIONS:
            await ctx.memory.log_event(
                ctx.session_id,
                actor="copilot",
                kind="unsupported_action",
                content=proposed_action,
            )
            return {
                "assistant_message": (
                    f"{reply.message}\n\n"
                    "This chat is currently read-only: it can explain, critique, "
                    "and suggest edits, but confirmed plan mutations are not "
                    "implemented in this product scope yet."
                ),
                "pending_action": None,
                "unsupported_action": proposed_action,
            }
        if proposed_action:
            user_id = (ctx.config or {}).get("user_id")
            if not user_id or not ctx.project_id or ctx.memory.artifact_repo is None:
                return {
                    "assistant_message": (
                        f"{reply.message}\n\n"
                        "I cannot create a pending plan mutation because this chat "
                        "session is missing persisted project/user context."
                    ),
                    "pending_action": None,
                    "unsupported_action": proposed_action,
                }
            try:
                validate_action_payload(ChatAction(proposed_action), reply.action_payload)
                preview = action_preview(ChatAction(proposed_action), reply.action_payload)
            except (ValueError, PydanticValidationError) as exc:
                await ctx.memory.log_event(
                    ctx.session_id,
                    actor="copilot",
                    kind="invalid_action_payload",
                    content=str(exc),
                )
                return {
                    "assistant_message": (
                        f"{reply.message}\n\n"
                        "I could not prepare a safe pending mutation because the "
                        "action payload was incomplete or invalid."
                    ),
                    "pending_action": None,
                    "unsupported_action": proposed_action,
                }
            pending = PendingChatAction(
                session_id=ctx.session_id,
                user_id=str(user_id),
                project_id=ctx.project_id,
                action=ChatAction(proposed_action),
                payload=reply.action_payload,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
            await ctx.memory.artifact_repo.save_pending_chat_action(pending)
            await ctx.memory.log_event(
                ctx.session_id,
                actor="copilot",
                kind="pending_action",
                content=preview,
                action_id=pending.id,
                action=proposed_action,
            )
            return {
                "assistant_message": reply.message,
                "pending_action": proposed_action,
                "pending_action_id": pending.id,
                "pending_action_preview": preview,
                "unsupported_action": None,
            }
        return {
            "assistant_message": reply.message,
            "pending_action": proposed_action,
            "pending_action_id": None,
            "pending_action_preview": None,
            "unsupported_action": None,
        }

    async def _maybe_apply(state: InteractiveState) -> dict[str, Any]:
        # Mutating chat tools are deliberately out of scope until they can
        # write persisted plans and audit every change.
        return {}

    graph.add_node("copilot", _copilot)
    graph.add_node("maybe_apply", _maybe_apply)
    graph.set_entry_point("copilot")
    graph.add_edge("copilot", "maybe_apply")
    graph.add_edge("maybe_apply", END)
    return graph.compile()
