CREATE TABLE IF NOT EXISTS episodic_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL,
    session_id   TEXT    NOT NULL,
    actor        TEXT    NOT NULL,
    kind         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    metadata     TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_episodic_session_ts
    ON episodic_events(session_id, ts);

CREATE INDEX IF NOT EXISTS idx_episodic_session_kind
    ON episodic_events(session_id, kind);
