"""Tests for M20 — OpenTelemetry instrumentation."""

from __future__ import annotations

import pytest

from ai_testplan_generator.config import Settings
from ai_testplan_generator.telemetry import otel as _otel_mod


# ---------------------------------------------------------------------------
# No-op path (OTEL_ENABLED=false, the default)
# ---------------------------------------------------------------------------


def test_init_tracing_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """init_tracing with otel_enabled=False must be a no-op — no imports, no network."""
    # Reset module state so a previous test doesn't bleed through.
    monkeypatch.setattr(_otel_mod, "_enabled", False)

    from ai_testplan_generator.telemetry.otel import init_tracing

    # Should complete without raising and without setting _enabled.
    init_tracing("test-service", "http://localhost:4318")
    assert _otel_mod._enabled is False


def test_get_tracer_returns_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_otel_mod, "_enabled", False)

    from ai_testplan_generator.telemetry.otel import get_tracer

    tracer = get_tracer("test")
    assert tracer is _otel_mod._noop_tracer


def test_noop_span_context_manager() -> None:
    """_NoopTracer.start_as_current_span must be usable as a context manager."""
    tracer = _otel_mod._NoopTracer()
    with tracer.start_as_current_span("test.op") as span:
        span.set_attribute("key", "value")
        span.set_attribute("count", 42)
        span.record_exception(RuntimeError("boom"))
    # No exception raised — that's the contract.


def test_noop_context_manager_propagates_exception() -> None:
    """Exceptions raised inside the span context must propagate unchanged."""
    tracer = _otel_mod._NoopTracer()
    with pytest.raises(ValueError, match="test error"):
        with tracer.start_as_current_span("op"):
            raise ValueError("test error")


def test_current_trace_context_returns_empty_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_otel_mod, "_enabled", False)

    from ai_testplan_generator.telemetry.otel import current_trace_context

    assert current_trace_context() == {}


# ---------------------------------------------------------------------------
# Agent span (in-memory exporter)
# ---------------------------------------------------------------------------


def test_agent_invoke_produces_span(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single BaseAgent.invoke call should produce a span named agent.<name>."""
    # Activate OTel with an in-memory exporter so no collector is needed.
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry import trace

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    monkeypatch.setattr(_otel_mod, "_enabled", True)

    import asyncio
    from ai_testplan_generator.agents.base import AgentContext, BaseAgent
    from ai_testplan_generator.config import Settings
    from tests.conftest import MockLLMGateway

    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
    )

    from ai_testplan_generator.memory.backends import (
        build_episodic_store,
        build_graph_store,
        build_semantic_store,
    )
    from ai_testplan_generator.memory.manager import MemoryManager

    async def _run() -> None:
        episodic = await build_episodic_store(settings)
        semantic = build_semantic_store(settings)
        graph = build_graph_store(settings)
        llm = MockLLMGateway()
        memory = MemoryManager(
            llm=llm,  # type: ignore[arg-type]
            settings=settings,
            episodic=episodic,
            semantic=semantic,
            graph=graph,
        )

        class _Ping(BaseAgent[str, str]):
            name = "ping"

            async def run(self, inp: str) -> str:
                return f"pong:{inp}"

        ctx = AgentContext(llm=llm, memory=memory, session_id="sess-test")  # type: ignore[arg-type]
        agent = _Ping(ctx)
        result = await agent.invoke("hello")
        assert result == "pong:hello"

    asyncio.get_event_loop().run_until_complete(_run())

    spans = exporter.get_finished_spans()
    span_names = [s.name for s in spans]
    assert any("agent.ping" in name for name in span_names), f"spans: {span_names}"

    # Cleanup
    monkeypatch.setattr(_otel_mod, "_enabled", False)
    trace.set_tracer_provider(trace.NoOpTracerProvider())


@pytest.mark.skip(reason="Requires a running OTLP collector endpoint")
def test_init_tracing_with_real_otlp_endpoint() -> None:
    """Integration test — requires OTEL_EXPORTER_OTLP_ENDPOINT to be reachable."""
    from ai_testplan_generator.telemetry.otel import init_tracing

    init_tracing("aitpg-api", "http://localhost:4318")
