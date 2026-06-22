# Troubleshooting

## Login Fails

Check that the database contains a user.

Run:

```bash
python scripts/create_admin.py
```

Then restart the backend if needed.

## Upload Returns 504 But Document Appears Later

This usually means the request timed out while background ingestion continued.

Check:

- backend logs;
- document table after refresh;
- number of chunks;
- worker status.

For presentations or quick validation, use smaller documents.

## `database is locked`

This can happen with SQLite when multiple writes happen at the same time.

Mitigations:

- avoid running multiple heavy generations at once;
- wait for ingestion to finish before starting generation;
- restart backend if a stale process holds the database;
- use a stronger database architecture for production.

## Generation Is Slow

Possible causes:

- large number of chunks;
- slow LLM provider;
- model rate limits;
- embedding rate limits;
- network instability.

Use shorter demo documents for presentations.

## Chat Has No Context

Check:

- selected project;
- uploaded documents;
- requirement extraction;
- generated plans;
- frontend chat context indicator;
- backend chat route configuration.

Ask a direct context question:

```text
What project am I working on and which documents are available?
```
