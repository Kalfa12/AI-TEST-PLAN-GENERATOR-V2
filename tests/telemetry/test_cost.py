"""Tests for M23 — LLM cost tracking aggregator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from ai_testplan_generator.telemetry.cost import (
    COST_TABLE,
    _compute_cost,
    get_cost_summary,
    get_project_spend_usd,
    record_usage,
)


# ---------------------------------------------------------------------------
# COST_TABLE sanity
# ---------------------------------------------------------------------------


def test_cost_table_contains_required_models() -> None:
    required = [
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-1-20250805",
        "gpt-4o",
        "gpt-4o-mini",
    ]
    for model in required:
        assert model in COST_TABLE, f"model '{model}' missing from COST_TABLE"


def test_cost_table_values_are_non_negative() -> None:
    for model, pricing in COST_TABLE.items():
        assert pricing["input"] >= 0, f"{model}: negative input price"
        assert pricing["output"] >= 0, f"{model}: negative output price"


def test_compute_cost_known_model() -> None:
    cost = _compute_cost("gpt-4o", input_tokens=1000, output_tokens=500)
    # gpt-4o: $0.0025/1k input, $0.01/1k output
    # (1000 * 0.0025 + 500 * 0.01) / 1000 = (2.5 + 5.0) / 1000 = 0.0075
    assert abs(cost - 0.0075) < 1e-9


def test_compute_cost_unknown_model_returns_zero() -> None:
    cost = _compute_cost("unknown-future-model", input_tokens=9999, output_tokens=9999)
    assert cost == 0.0


# ---------------------------------------------------------------------------
# record_usage + get_cost_summary round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_and_retrieve_usage(tmp_path: Path) -> None:
    db = str(tmp_path / "test_usage.db")

    await record_usage(
        db,
        session_id="sess-001",
        project_id="proj-abc",
        user_id="usr-xyz",
        model="gpt-4o",
        role="balanced",
        input_tokens=200,
        output_tokens=100,
    )
    await record_usage(
        db,
        session_id="sess-002",
        project_id="proj-abc",
        user_id="usr-xyz",
        model="gpt-4o-mini",
        role="fast",
        input_tokens=50,
        output_tokens=25,
    )

    summary = await get_cost_summary(
        db,
        from_ts="2020-01-01T00:00:00+00:00",
        to_ts="2099-12-31T23:59:59+00:00",
        group_by="project",
    )

    assert len(summary) == 1
    row = summary[0]
    assert row["project"] == "proj-abc"
    assert row["call_count"] == 2
    assert row["input_tokens"] == 250
    assert row["output_tokens"] == 125
    assert row["cost_usd"] > 0


@pytest.mark.asyncio
async def test_get_cost_summary_group_by_model(tmp_path: Path) -> None:
    db = str(tmp_path / "test_model.db")

    await record_usage(
        db,
        session_id="s1",
        project_id="p1",
        user_id=None,
        model="gpt-4o",
        role="balanced",
        input_tokens=100,
        output_tokens=50,
    )
    await record_usage(
        db,
        session_id="s2",
        project_id="p1",
        user_id=None,
        model="gpt-4o-mini",
        role="fast",
        input_tokens=100,
        output_tokens=50,
    )

    summary = await get_cost_summary(
        db,
        from_ts="2020-01-01T00:00:00+00:00",
        to_ts="2099-12-31T23:59:59+00:00",
        group_by="model",
    )
    models_returned = {row["model"] for row in summary}
    assert "gpt-4o" in models_returned
    assert "gpt-4o-mini" in models_returned


@pytest.mark.asyncio
async def test_get_project_spend_usd_filters_project(tmp_path: Path) -> None:
    db = str(tmp_path / "project_spend.db")

    await record_usage(
        db,
        session_id="s1",
        project_id="p1",
        user_id=None,
        model="gpt-4o",
        role="balanced",
        input_tokens=1000,
        output_tokens=500,
    )
    await record_usage(
        db,
        session_id="s2",
        project_id="p2",
        user_id=None,
        model="gpt-4o",
        role="balanced",
        input_tokens=1000,
        output_tokens=500,
    )

    spend = await get_project_spend_usd(
        db,
        project_id="p1",
        from_ts="2020-01-01T00:00:00+00:00",
        to_ts="2099-12-31T23:59:59+00:00",
    )

    assert abs(spend - _compute_cost("gpt-4o", 1000, 500)) < 1e-9


@pytest.mark.asyncio
async def test_get_cost_summary_empty_when_db_missing(tmp_path: Path) -> None:
    db = str(tmp_path / "nonexistent.db")
    summary = await get_cost_summary(
        db,
        from_ts="2020-01-01T00:00:00+00:00",
        to_ts="2099-12-31T23:59:59+00:00",
    )
    assert summary == []


@pytest.mark.asyncio
async def test_record_usage_graceful_on_bad_path() -> None:
    """record_usage must not raise even when db_path is unwritable."""
    # /dev/null is not a valid SQLite path — record_usage should swallow the error.
    await record_usage(
        "/dev/null/impossible/path.db",
        session_id=None,
        project_id=None,
        user_id=None,
        model="mock-model",
        role="fast",
        input_tokens=1,
        output_tokens=1,
    )


@pytest.mark.asyncio
async def test_get_cost_summary_respects_time_range(tmp_path: Path) -> None:
    db = str(tmp_path / "range.db")

    await record_usage(
        db,
        session_id=None,
        project_id="p-old",
        user_id=None,
        model="gpt-4o",
        role="balanced",
        input_tokens=10,
        output_tokens=5,
    )

    # Query a time range in the far past — should return nothing.
    summary = await get_cost_summary(
        db,
        from_ts="2000-01-01T00:00:00+00:00",
        to_ts="2000-12-31T23:59:59+00:00",
    )
    assert summary == []


# ---------------------------------------------------------------------------
# Admin endpoint smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_costs_endpoint(tmp_path: Path) -> None:
    """GET /admin/costs should return 200 for an admin user."""
    from httpx import ASGITransport, AsyncClient

    from ai_testplan_generator.api.app import create_app
    from ai_testplan_generator.api.deps import (
        get_current_user,
        get_settings,
    )
    from ai_testplan_generator.config import Settings
    from ai_testplan_generator.domain.users import User

    db = str(tmp_path / "app.db")
    settings = Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
        APP_DB_PATH=db,
        COST_TRACKING_ENABLED=True,
    )

    admin_user = User(
        id="usr_admin",
        email="admin@test.local",
        display_name="Admin",
        is_admin=True,
    )

    app = create_app(settings=settings)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_settings] = lambda: settings

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/admin/costs",
            params={"from": "2020-01-01T00:00:00Z", "to": "2099-12-31T23:59:59Z"},
        )

    assert response.status_code == 200
    assert isinstance(response.json(), list)
