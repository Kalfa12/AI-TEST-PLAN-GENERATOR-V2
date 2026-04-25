-- Migration 004: LLM usage and cost tracking table (M23)
CREATE TABLE IF NOT EXISTS llm_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    session_id    TEXT,
    project_id    TEXT,
    user_id       TEXT,
    model         TEXT    NOT NULL,
    role          TEXT    NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL    NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_ts      ON llm_usage(ts);
CREATE INDEX IF NOT EXISTS idx_llm_usage_project ON llm_usage(project_id, ts);
