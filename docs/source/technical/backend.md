# Backend

The backend is a FastAPI application.

Application factory:

```text
ai_testplan_generator.api.app:create_app
```

Local command:

```bash
uvicorn ai_testplan_generator.api.app:create_app --factory --reload --port 8000
```

## Startup

At startup, the application builds:

- settings;
- logging;
- telemetry;
- memory backends;
- blob store;
- LLM gateway;
- ingestion pipeline;
- general knowledge base service;
- project repository;
- user repository;
- job repository;
- artifact repository;
- event broker;
- job queue.

## Routers

The backend exposes routers for:

- authentication;
- projects;
- documents;
- plans;
- planning;
- traceability;
- quality;
- chat;
- events;
- admin;
- health.

## Jobs

Long-running work such as plan generation can run through a job queue.

Development mode can use an in-process fake queue. Production-style deployments use Redis and ARQ workers.

## Storage

The backend uses:

- SQLite for local application data;
- local filesystem blob storage by default;
- optional S3-compatible storage;
- optional Qdrant for semantic memory;
- optional Neo4j for graph memory.
