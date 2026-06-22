# Architecture

The application has four main layers:

- React frontend;
- FastAPI backend;
- AI brain and memory layer;
- storage and operational services.

```{mermaid}
flowchart LR
    U["User"] --> F["React frontend"]
    F --> A["FastAPI API"]
    A --> Q["Job queue"]
    A --> B["AI Brain"]
    Q --> B
    B --> L["LLM Gateway"]
    B --> M["Memory Manager"]
    M --> S["Semantic Store"]
    M --> E["Episodic Store"]
    M --> G["Traceability Graph"]
    A --> DB["SQLite app database"]
    A --> BS["Blob storage"]
```

## Frontend

The frontend is located in `frontend/`.

Main technologies:

- React 18;
- TypeScript;
- Vite;
- TanStack Query;
- TanStack Router;
- Tailwind CSS.

## Backend

The backend is located in `src/ai_testplan_generator/`.

Main technologies:

- FastAPI;
- Pydantic;
- SQLite repositories;
- async services;
- LiteLLM;
- LangGraph-style agent orchestration;
- pluggable memory backends.

## Runtime Services

The Docker Compose stack includes:

- frontend service;
- API service;
- worker service;
- Redis;
- Qdrant;
- Neo4j;
- optional Prometheus, Grafana, and Jaeger.

## Main Backend Modules

| Module | Responsibility |
| --- | --- |
| `api/` | FastAPI app, routers, schemas, auth, middleware |
| `agents/` | AI agent implementations |
| `pipelines/` | autonomous and interactive generation flows |
| `ingestion/` | document loading, extraction, chunking |
| `memory/` | episodic, semantic, and graph memory |
| `domain/` | repositories and domain models |
| `models/` | Pydantic model definitions |
| `llm/` | provider-neutral LLM gateway |
| `telemetry/` | cost, metrics, logs, tracing |
| `storage/` | local and S3-like blob storage |
