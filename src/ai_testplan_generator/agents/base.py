"""Base agent contract.

Every agent takes an `AgentContext` and returns a typed output. Agents
never talk to providers directly - only via the LLM gateway - and never
own storage - only the MemoryManager does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    settings: Any | None = None
    project_repo: Any | None = None
    # Optional EventBroker — when set, per-agent start/done/error events are
    # published to the session SSE stream so the frontend can track progress.
    event_broker: Any | None = field(default=None, compare=False)

    async def project_industry(self) -> str:
        if self.config and self.config.get("industry"):
            return str(self.config["industry"])
        if self.project_repo is None or self.project_id is None:
            return "generic"
        try:
            project = await self.project_repo.get_project(self.project_id)
        except Exception:  # noqa: BLE001
            return "generic"
        industry = getattr(project, "industry", None)
        if industry is None:
            return "generic"
        return str(getattr(industry, "value", industry))


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

    async def _publish(self, kind: str, content: str) -> None:
        if self.ctx.event_broker is None:
            return
        try:
            await self.ctx.event_broker.publish(
                f"session:{self.ctx.session_id}",
                {"kind": kind, "actor": self.name, "content": content},
            )
        except Exception:  # noqa: BLE001
            pass

    async def _enforce_budget(self) -> None:
        from ai_testplan_generator.telemetry.budget import enforce_project_llm_budget

        await enforce_project_llm_budget(
            settings=self.ctx.settings,
            project_repo=self.ctx.project_repo,
            project_id=self.ctx.project_id,
        )

    async def invoke(self, inp: TIn) -> TOut:
        import time as _time

        from ai_testplan_generator.telemetry.otel import get_tracer as _get_tracer

        _tracer = _get_tracer(__name__)
        _t0 = _time.perf_counter()
        _outcome = "success"

        context_keys: list[str] = []
        try:
            from structlog.contextvars import bind_contextvars

            values: dict[str, str] = {"session_id": self.ctx.session_id}
            if self.ctx.project_id is not None:
                values["project_id"] = self.ctx.project_id
            bind_contextvars(**values)
            context_keys = list(values)
        except Exception:  # noqa: BLE001
            context_keys = []

        try:
            await self._enforce_budget()

            with _tracer.start_as_current_span(f"agent.{self.name}") as _span:
                _span.set_attribute("agent.name", self.name)
                _span.set_attribute("session_id", self.ctx.session_id)
                if self.ctx.project_id is not None:
                    _span.set_attribute("project_id", self.ctx.project_id)

                await self.ctx.memory.log_event(
                    self.ctx.session_id,
                    actor=self.name,
                    kind="agent_start",
                    content=f"{self.name} invoked",
                )
                await self._publish("agent_start", f"{self.name} started")
                try:
                    out = await self.run(inp)
                except Exception as e:
                    _log.exception("agent_failed", agent=self.name, error=str(e))
                    _outcome = "error"
                    _span.record_exception(e)
                    await self.ctx.memory.log_event(
                        self.ctx.session_id,
                        actor=self.name,
                        kind="agent_error",
                        content=str(e),
                    )
                    await self._publish("agent_error", str(e))
                    raise
                finally:
                    _elapsed = _time.perf_counter() - _t0
                    try:
                        from ai_testplan_generator.telemetry import metrics as _m

                        if _m._registry is not None:
                            _m.agent_runs_total().labels(
                                agent=self.name, outcome=_outcome
                            ).inc()
                            _m.agent_duration_seconds().labels(agent=self.name).observe(
                                _elapsed
                            )
                    except Exception:  # noqa: BLE001
                        pass

            await self.ctx.memory.log_event(
                self.ctx.session_id,
                actor=self.name,
                kind="agent_done",
                content=f"{self.name} returned",
            )
            await self._publish("agent_done", f"{self.name} done")
            return out  # type: ignore[return-value]
        finally:
            if context_keys:
                try:
                    from structlog.contextvars import unbind_contextvars

                    unbind_contextvars(*context_keys)
                except Exception:  # noqa: BLE001
                    pass
