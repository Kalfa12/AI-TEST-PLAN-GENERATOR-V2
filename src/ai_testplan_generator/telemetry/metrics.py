"""Prometheus metrics registry (M21).

All metric objects live inside an isolated ``CollectorRegistry`` created by
``init_metrics()``.  Nothing is added to the default global registry, which
keeps test suites isolated and prevents duplicate-registration errors when
``init_metrics()`` is called multiple times in the same process (e.g. during
parametrised tests).

Usage
-----
    from ai_testplan_generator.telemetry.metrics import init_metrics, get_registry
    from prometheus_client import generate_latest

    init_metrics()
    output = generate_latest(get_registry())
"""

from __future__ import annotations

from typing import TypeVar

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

_MetricT = TypeVar("_MetricT")

# ---------------------------------------------------------------------------
# Module-level singletons — set by init_metrics()
# ---------------------------------------------------------------------------

_registry: CollectorRegistry | None = None

# HTTP layer
_requests_total: Counter | None = None
_request_duration_seconds: Histogram | None = None

# LLM gateway
_llm_calls_total: Counter | None = None
_llm_tokens_total: Counter | None = None
_llm_latency_seconds: Histogram | None = None

# Agent layer
_agent_runs_total: Counter | None = None
_agent_duration_seconds: Histogram | None = None

# Ingestion
_ingest_docs_total: Counter | None = None
_ingest_chunks_total: Counter | None = None

# Job queue
_job_queue_depth: Gauge | None = None
_job_duration_seconds: Histogram | None = None

# Quality / defects
_defects_total: Counter | None = None

_LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)


def init_metrics() -> None:
    """Create a fresh isolated registry and register all metric collectors.

    Safe to call multiple times — each call replaces the previous registry,
    which is intentional for test isolation.
    """
    global _registry
    global _requests_total, _request_duration_seconds
    global _llm_calls_total, _llm_tokens_total, _llm_latency_seconds
    global _agent_runs_total, _agent_duration_seconds
    global _ingest_docs_total, _ingest_chunks_total
    global _job_queue_depth, _job_duration_seconds
    global _defects_total

    reg = CollectorRegistry(auto_describe=False)

    _requests_total = Counter(
        "aitpg_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
        registry=reg,
    )
    _request_duration_seconds = Histogram(
        "aitpg_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        buckets=_LATENCY_BUCKETS,
        registry=reg,
    )
    _llm_calls_total = Counter(
        "aitpg_llm_calls_total",
        "Total LLM completion calls",
        ["model", "role", "outcome"],
        registry=reg,
    )
    _llm_tokens_total = Counter(
        "aitpg_llm_tokens_total",
        "Total LLM tokens consumed",
        ["model", "role", "direction"],
        registry=reg,
    )
    _llm_latency_seconds = Histogram(
        "aitpg_llm_latency_seconds",
        "LLM call latency in seconds",
        ["model", "role"],
        buckets=_LATENCY_BUCKETS,
        registry=reg,
    )
    _agent_runs_total = Counter(
        "aitpg_agent_runs_total",
        "Total agent invocations",
        ["agent", "outcome"],
        registry=reg,
    )
    _agent_duration_seconds = Histogram(
        "aitpg_agent_duration_seconds",
        "Agent run duration in seconds",
        ["agent"],
        buckets=_LATENCY_BUCKETS,
        registry=reg,
    )
    _ingest_docs_total = Counter(
        "aitpg_ingest_docs_total",
        "Total documents ingested",
        ["kind", "outcome"],
        registry=reg,
    )
    _ingest_chunks_total = Counter(
        "aitpg_ingest_chunks_total",
        "Total chunks produced during ingestion",
        registry=reg,
    )
    _job_queue_depth = Gauge(
        "aitpg_job_queue_depth",
        "Estimated number of pending jobs by task name",
        ["task"],
        registry=reg,
    )
    _job_duration_seconds = Histogram(
        "aitpg_job_duration_seconds",
        "Background job duration in seconds",
        ["task", "outcome"],
        buckets=_LATENCY_BUCKETS,
        registry=reg,
    )
    _defects_total = Counter(
        "aitpg_defects_total",
        "Total defects identified by the quality layer",
        ["defect_type", "severity", "detector"],
        registry=reg,
    )

    _registry = reg


# ---------------------------------------------------------------------------
# Accessor helpers — raise if init_metrics() was not called
# ---------------------------------------------------------------------------


def get_registry() -> CollectorRegistry:
    if _registry is None:
        init_metrics()
    assert _registry is not None
    return _registry


def _require(metric: "_MetricT | None", name: str) -> "_MetricT":
    if metric is None:
        raise RuntimeError(f"Metric '{name}' not initialised — call init_metrics() first")
    return metric


def requests_total() -> Counter:
    return _require(_requests_total, "aitpg_requests_total")


def request_duration_seconds() -> Histogram:
    return _require(_request_duration_seconds, "aitpg_request_duration_seconds")


def llm_calls_total() -> Counter:
    return _require(_llm_calls_total, "aitpg_llm_calls_total")


def llm_tokens_total() -> Counter:
    return _require(_llm_tokens_total, "aitpg_llm_tokens_total")


def llm_latency_seconds() -> Histogram:
    return _require(_llm_latency_seconds, "aitpg_llm_latency_seconds")


def agent_runs_total() -> Counter:
    return _require(_agent_runs_total, "aitpg_agent_runs_total")


def agent_duration_seconds() -> Histogram:
    return _require(_agent_duration_seconds, "aitpg_agent_duration_seconds")


def ingest_docs_total() -> Counter:
    return _require(_ingest_docs_total, "aitpg_ingest_docs_total")


def ingest_chunks_total() -> Counter:
    return _require(_ingest_chunks_total, "aitpg_ingest_chunks_total")


def job_queue_depth() -> Gauge:
    return _require(_job_queue_depth, "aitpg_job_queue_depth")


def job_duration_seconds() -> Histogram:
    return _require(_job_duration_seconds, "aitpg_job_duration_seconds")


def defects_total() -> Counter:
    return _require(_defects_total, "aitpg_defects_total")
