"""OpenTelemetry tracing helpers (M20).

All opentelemetry-sdk imports are lazy (inside functions) so importing this
module never triggers OTLP network calls in test environments where
OTEL_ENABLED=false (the default).

Usage
-----
    from ai_testplan_generator.telemetry.otel import init_tracing, get_tracer

    init_tracing(cfg.otel_service_name, cfg.otel_exporter_otlp_endpoint)
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my.operation") as span:
        span.set_attribute("key", "value")
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

# ---------------------------------------------------------------------------
# No-op tracer (used when OTEL_ENABLED=false — zero overhead, no imports)
# ---------------------------------------------------------------------------

_enabled: bool = False


class _NoopSpan:
    """Drop-in span that silently discards all operations."""

    def set_attribute(self, key: str, value: str | int | float | bool | bytes) -> "_NoopSpan":
        return self

    def record_exception(
        self,
        exception: BaseException,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass


class _NoopContextManager:
    def __init__(self) -> None:
        self._span = _NoopSpan()

    def __enter__(self) -> _NoopSpan:
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _NoopTracer:
    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoopContextManager:
        return _NoopContextManager()


_noop_tracer = _NoopTracer()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_tracing(service_name: str, exporter_endpoint: str) -> None:
    """Initialise the global OTel tracer provider.

    This is a no-op when ``OTEL_ENABLED=false`` (the default) so test suites
    never attempt to reach a collector.
    """
    global _enabled

    # Lazy import so otel.py is safe to import without opentelemetry installed.
    from ai_testplan_generator.config import get_settings

    if not get_settings().otel_enabled:
        return

    _enabled = True

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if exporter_endpoint:
        exporter = OTLPSpanExporter(endpoint=exporter_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI and httpx if available.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass


def get_tracer(name: str) -> Any:
    """Return a tracer for the given instrumentation scope.

    Returns a no-op tracer when OTel is disabled so callers never need to
    guard against ``None``.
    """
    if not _enabled:
        return _noop_tracer
    from opentelemetry import trace

    return trace.get_tracer(name)


def current_trace_context() -> dict[str, str]:
    """Return trace_id and span_id from the active OTel span (empty when disabled)."""
    if not _enabled:
        return {}
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return {}
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
        }
    except Exception:
        return {}
