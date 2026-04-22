"""Base agent contract.

Every agent takes an `AgentContext` and returns a typed output. Agents
never talk to providers directly - only via the LLM gateway - and never
own storage - only the MemoryManager does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import structlog

from ai_testplan_generator.llm import LLMGateway
from ai_testplan_generator.memory.manager import MemoryManager

_log = structlog.get_logger(__name__)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


@dataclass
class AgentContext:
    """Shared runtime handles passed to every agent."""

    llm: LLMGateway
    memory: MemoryManager
    session_id: str
    project_id: str | None = None
    config: dict[str, Any] | None = None


class BaseAgent(ABC, Generic[TIn, TOut]):
    """Base class for typed async agents.

    Subclasses implement `run`. `invoke` wraps `run` with episodic
    logging so the orchestrator has a full audit trail.
    """

    name: str = "agent"

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    @abstractmethod
    async def run(self, inp: TIn) -> TOut: ...

    async def invoke(self, inp: TIn) -> TOut:
        await self.ctx.memory.log_event(
            self.ctx.session_id,
            actor=self.name,
            kind="agent_start",
            content=f"{self.name} invoked",
        )
        try:
            out = await self.run(inp)
        except Exception as e:
            _log.exception("agent_failed", agent=self.name, error=str(e))
            await self.ctx.memory.log_event(
                self.ctx.session_id,
                actor=self.name,
                kind="agent_error",
                content=str(e),
            )
            raise
        await self.ctx.memory.log_event(
            self.ctx.session_id,
            actor=self.name,
            kind="agent_done",
            content=f"{self.name} returned",
        )
        return out
