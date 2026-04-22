"""Interactive LangGraph.

A lean graph for the chat/copilot mode. One turn = one pass through the
graph. The heavy lifting lives inside `CopilotAgent`; the graph gives us
a stable integration surface (checkpointing, interrupts, streaming) and
a natural seam to later add a confirmation node for mutating actions.

Topology:
    START -> copilot -> maybe_apply -> END

`maybe_apply` inspects the copilot's `proposed_action`. If an action
needs confirmation, it stays in a waiting state and surfaces the
pending action to the caller; otherwise it applies non-mutating actions
directly.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ai_testplan_generator.agents import CopilotAgent, InteractiveState
from ai_testplan_generator.agents.base import AgentContext


def build_interactive_graph(ctx: AgentContext) -> Any:
    copilot = CopilotAgent(ctx)
    graph: StateGraph = StateGraph(InteractiveState)

    async def _copilot(state: InteractiveState) -> dict[str, Any]:
        reply = await copilot.invoke(
            CopilotAgent.Input(user_message=state.user_message)
        )
        return {
            "assistant_message": reply.message,
            "pending_action": (
                reply.proposed_action
                if reply.needs_confirmation and reply.proposed_action != "none"
                else None
            ),
        }

    async def _maybe_apply(state: InteractiveState) -> dict[str, Any]:
        # Non-mutating by default. Concrete mutations (add_test_case etc.)
        # are resolved in a later phase when the user confirms - at which
        # point a caller will re-enter the graph with a flag to apply.
        return {}

    graph.add_node("copilot", _copilot)
    graph.add_node("maybe_apply", _maybe_apply)
    graph.set_entry_point("copilot")
    graph.add_edge("copilot", "maybe_apply")
    graph.add_edge("maybe_apply", END)
    return graph.compile()
