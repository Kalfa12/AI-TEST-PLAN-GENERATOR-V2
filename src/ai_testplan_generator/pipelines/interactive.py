"""InteractivePipeline - chat/copilot driver.

Typical usage:

    brain = Brain.build()
    chat = InteractivePipeline(brain)
    session = chat.session(project_id="proj-42")
    reply = await session.ask("What standards are referenced in this corpus?")
    reply = await session.ask("Draft a test for REQ-4.2.1.")
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ai_testplan_generator.agents import InteractiveState
from ai_testplan_generator.graphs import build_interactive_graph
from ai_testplan_generator.pipelines.brain import Brain


@dataclass
class ChatReply:
    assistant_message: str
    pending_action: str | None = None
    pending_action_id: str | None = None
    pending_action_preview: str | None = None
    unsupported_action: str | None = None


class InteractiveSession:
    def __init__(
        self,
        brain: Brain,
        *,
        project_id: str | None,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        self._brain = brain
        self._project_id = project_id
        self._user_id = user_id
        self.session_id = session_id
        self.rebind(project_id=project_id, user_id=user_id)

    def rebind(self, *, project_id: str | None, user_id: str | None = None) -> None:
        self._project_id = project_id
        self._user_id = user_id
        ctx = self._brain.context(session_id=self.session_id, project_id=project_id)
        ctx.config = {**(ctx.config or {}), "user_id": user_id}
        self._graph = build_interactive_graph(ctx)

    async def ask(self, user_message: str) -> ChatReply:
        state = InteractiveState(
            session_id=self.session_id,
            project_id=self._project_id,
            user_message=user_message,
        )
        out = await self._graph.ainvoke(state)
        out_state = out if isinstance(out, InteractiveState) else InteractiveState.model_validate(out)
        return ChatReply(
            assistant_message=out_state.assistant_message,
            pending_action=out_state.pending_action,
            pending_action_id=out_state.pending_action_id,
            pending_action_preview=out_state.pending_action_preview,
            unsupported_action=out_state.unsupported_action,
        )


class InteractivePipeline:
    def __init__(self, brain: Brain) -> None:
        self._brain = brain
        self._sessions: dict[str, InteractiveSession] = {}

    def session(
        self,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> InteractiveSession:
        sid = session_id or f"chat_{uuid4().hex[:10]}"
        if sid not in self._sessions:
            self._sessions[sid] = InteractiveSession(
                self._brain, project_id=project_id, session_id=sid, user_id=user_id
            )
        session = self._sessions[sid]
        if session._project_id != project_id or session._user_id != user_id:
            session.rebind(project_id=project_id, user_id=user_id)
        return session

    async def ask(
        self,
        user_message: str,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> ChatReply:
        return await self.session(
            project_id=project_id, session_id=session_id, user_id=user_id
        ).ask(user_message)
