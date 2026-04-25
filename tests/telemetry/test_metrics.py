"""Tests for M21 — Prometheus metrics."""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest  # type: ignore[import-untyped]

from ai_testplan_generator.telemetry.metrics import (
    get_registry,
    init_metrics,
    llm_calls_total,
    llm_tokens_total,
    agent_runs_total,
    requests_total,
    request_duration_seconds,
)


@pytest.fixture(autouse=True)
def fresh_registry() -> None:
    """Re-initialise metrics before each test for isolation."""
    init_metrics()


# ---------------------------------------------------------------------------
# Registry and metric name presence
# ---------------------------------------------------------------------------


def test_init_metrics_creates_registry() -> None:
    reg = get_registry()
    assert reg is not None


def test_generate_latest_contains_all_metric_names() -> None:
    output = generate_latest(get_registry()).decode()
    expected_names = [
        "aitpg_requests_total",
        "aitpg_request_duration_seconds",
        "aitpg_llm_calls_total",
        "aitpg_llm_tokens_total",
        "aitpg_llm_latency_seconds",
        "aitpg_agent_runs_total",
        "aitpg_agent_duration_seconds",
        "aitpg_ingest_docs_total",
        "aitpg_ingest_chunks_total",
        "aitpg_job_queue_depth",
        "aitpg_job_duration_seconds",
    ]
    for name in expected_names:
        assert name in output, f"metric '{name}' missing from /metrics output"


# ---------------------------------------------------------------------------
# Counter increments
# ---------------------------------------------------------------------------


def test_llm_calls_counter_increments() -> None:
    before = llm_calls_total().labels(
        model="mock-model", role="balanced", outcome="success"
    )._value.get()
    llm_calls_total().labels(model="mock-model", role="balanced", outcome="success").inc()
    after = llm_calls_total().labels(
        model="mock-model", role="balanced", outcome="success"
    )._value.get()
    assert after == before + 1


def test_llm_tokens_counter_increments() -> None:
    llm_tokens_total().labels(model="mock-model", role="fast", direction="input").inc(100)
    val = llm_tokens_total().labels(
        model="mock-model", role="fast", direction="input"
    )._value.get()
    assert val >= 100


def test_agent_runs_counter_increments() -> None:
    agent_runs_total().labels(agent="ping", outcome="success").inc()
    val = agent_runs_total().labels(agent="ping", outcome="success")._value.get()
    assert val >= 1


# ---------------------------------------------------------------------------
# HTTP metrics via test client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metrics_endpoint_returns_200(tmp_path: "pytest.Path") -> None:
    """GET /metrics returns 200 with aitpg_requests_total in the body."""
    from httpx import ASGITransport, AsyncClient

    from ai_testplan_generator.api.app import create_app
    from ai_testplan_generator.config import Settings

    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        APP_DB_PATH=str(tmp_path / "app.db"),
        METRICS_ENABLED=True,
    )

    app = create_app(settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert b"aitpg_requests_total" in response.content


@pytest.mark.asyncio
async def test_get_metrics_returns_404_when_disabled(tmp_path: "pytest.Path") -> None:
    """GET /metrics returns 404 when METRICS_ENABLED=false."""
    from httpx import ASGITransport, AsyncClient

    from ai_testplan_generator.api.app import create_app
    from ai_testplan_generator.config import Settings

    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        APP_DB_PATH=str(tmp_path / "app.db"),
        METRICS_ENABLED=False,
    )

    app = create_app(settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Multiple init_metrics calls don't explode (test isolation)
# ---------------------------------------------------------------------------


def test_init_metrics_is_idempotent() -> None:
    """Calling init_metrics twice must not raise DuplicateRegistration."""
    init_metrics()
    init_metrics()
    assert get_registry() is not None
