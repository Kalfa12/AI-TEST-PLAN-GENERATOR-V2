CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    user_id      TEXT,
    project_id   TEXT,
    action       TEXT NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    status       INTEGER NOT NULL,
    ip           TEXT,
    user_agent   TEXT,
    metadata     TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_events(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON audit_events(action, ts);
