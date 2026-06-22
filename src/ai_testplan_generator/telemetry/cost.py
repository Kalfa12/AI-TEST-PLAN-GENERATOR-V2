"""LLM cost tracking aggregator (M23).

Writes one row per LLM call to the ``llm_usage`` SQLite table (schema in
migrations/004_llm_usage.sql) and exposes a summary query used by the admin
endpoint.

Pricing last updated: 2026-06-21.  All prices in USD per 1 000 tokens.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import aiosqlite
import structlog

_log = structlog.get_logger(__name__)

_SQLITE_BUSY_TIMEOUT_MS = 30_000

# ---------------------------------------------------------------------------
# Pricing table  (model_id -> {input: $/1k, output: $/1k})
# ---------------------------------------------------------------------------

COST_TABLE: dict[str, dict[str, float]] = {
    # Anthropic Claude 4 family
    "claude-opus-4-7": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5": {"input": 0.00025, "output": 0.00125},
    # Anthropic Claude 3.5 / 3 family (aliases used in config defaults)
    "claude-opus-4-1-20250805": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5-20251001": {"input": 0.00025, "output": 0.00125},
    # Legacy Claude 3.5 models
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    # OpenAI GPT-4o family
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o-2024-11-20": {"input": 0.0025, "output": 0.01},
    # OpenAI GPT-4 turbo
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4-turbo-2024-04-09": {"input": 0.01, "output": 0.03},
    # Google Gemini
    "gemini/gemini-2.5-pro": {"input": 0.00125, "output": 0.01},
    "gemini/gemini-2.5-flash": {"input": 0.000075, "output": 0.0003},
    # OpenRouter aliases used by the local dev configuration.
    "deepseek-v4-flash": {"input": 0.00009, "output": 0.00018},
    "deepseek/deepseek-v4-flash": {"input": 0.00009, "output": 0.00018},
    "gemma-4-31b-it": {"input": 0.00012, "output": 0.00035},
    "google/gemma-4-31b-it": {"input": 0.00012, "output": 0.00035},
    # Test/mock models — zero cost
    "mock-model": {"input": 0.0, "output": 0.0},
}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = COST_TABLE.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000.0


# ---------------------------------------------------------------------------
# Migration — run inline on first use
# ---------------------------------------------------------------------------

_MIGRATION_SQL = (
    Path(__file__).parent.parent / "memory" / "backends" / "migrations" / "004_llm_usage.sql"
)

_migrated_dbs: set[str] = set()


async def _ensure_schema(conn: aiosqlite.Connection, db_path: str) -> None:
    if db_path in _migrated_dbs:
        return
    sql = _MIGRATION_SQL.read_text()
    await conn.executescript(sql)
    await conn.commit()
    _migrated_dbs.add(db_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def record_usage(
    db_path: str,
    *,
    session_id: str | None,
    project_id: str | None,
    user_id: str | None,
    model: str,
    role: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Append one usage row to the llm_usage table.

    Designed to be called as a fire-and-forget task:
        asyncio.create_task(record_usage(...))
    """
    cost = _compute_cost(model, input_tokens, output_tokens)
    ts = datetime.now(timezone.utc).isoformat()
    try:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(db_path, timeout=30.0) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
            await _ensure_schema(conn, db_path)
            await conn.execute(
                """INSERT INTO llm_usage
                   (ts, session_id, project_id, user_id, model, role,
                    input_tokens, output_tokens, cost_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, session_id, project_id, user_id, model, role,
                 input_tokens, output_tokens, cost),
            )
            await conn.commit()
    except Exception as exc:
        _log.warning("llm_usage_write_failed", error=str(exc))


async def get_cost_summary(
    db_path: str,
    *,
    from_ts: str,
    to_ts: str,
    group_by: Literal["project", "user", "model"] = "project",
) -> list[dict[str, Any]]:
    """Return aggregated cost and token usage grouped by the chosen dimension.

    Parameters
    ----------
    from_ts / to_ts:
        ISO-8601 timestamps (inclusive range).
    group_by:
        "project" → group by project_id
        "user"    → group by user_id
        "model"   → group by model
    """
    col_map = {"project": "project_id", "user": "user_id", "model": "model"}
    group_col = col_map[group_by]

    path = Path(db_path)
    if not path.exists():
        return []

    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        await conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        await _ensure_schema(conn, db_path)
        conn.row_factory = aiosqlite.Row
        sql = f"""
            SELECT
                {group_col}                       AS group_key,
                SUM(input_tokens)                 AS input_tokens,
                SUM(output_tokens)                AS output_tokens,
                SUM(cost_usd)                     AS cost_usd,
                COUNT(*)                          AS call_count
            FROM llm_usage
            WHERE ts >= ? AND ts <= ?
            GROUP BY {group_col}
            ORDER BY cost_usd DESC
        """
        cursor = await conn.execute(sql, (from_ts, to_ts))
        rows = await cursor.fetchall()

    return [
        {
            group_by: row["group_key"],
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "cost_usd": float(row["cost_usd"] or 0.0),
            "call_count": int(row["call_count"] or 0),
        }
        for row in rows
    ]


def current_month_bounds(now: datetime | None = None) -> tuple[str, str]:
    """Return inclusive/exclusive UTC ISO bounds for the current calendar month."""
    anchor = now or datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    anchor = anchor.astimezone(timezone.utc)
    start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start.isoformat(), next_month.isoformat()


async def get_project_spend_usd(
    db_path: str,
    *,
    project_id: str,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> float:
    """Return total LLM spend for one project in a time range.

    Defaults to the current UTC month, matching project budget enforcement.
    """
    if from_ts is None or to_ts is None:
        month_start, month_end = current_month_bounds()
        from_ts = from_ts or month_start
        to_ts = to_ts or month_end

    path = Path(db_path)
    if not path.exists():
        return 0.0

    async with aiosqlite.connect(db_path) as conn:
        await _ensure_schema(conn, db_path)
        cursor = await conn.execute(
            """
            SELECT SUM(cost_usd)
            FROM llm_usage
            WHERE project_id = ? AND ts >= ? AND ts < ?
            """,
            (project_id, from_ts, to_ts),
        )
        row = await cursor.fetchone()

    return float(row[0] or 0.0)
