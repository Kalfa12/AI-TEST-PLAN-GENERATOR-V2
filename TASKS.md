# AI Test Plan Generator — Implementation Tasks

> **Strategy:** We implement one module at a time, fully, before moving to the next.
> Each task is checked off (`[x]`) as it's completed.

---

## Module Overview (Priority Order)

| # | Module | Status | Why this order |
|---|--------|--------|----------------|
| 1 | **HTTP API (FastAPI)** | ✅ Done | Makes the brain accessible to any frontend/client — highest leverage |
| 2 | **Containerisation (Docker)** | ✅ Done | Required for deployment; natural follow-up to having an API |
| 3 | **Persistent Vector Store (Qdrant)** | ✅ Done | Data survives restarts — needed before real use |
| 4 | **Persistent Episodic Store (SQLite)** | ✅ Done | Session history persistence |
| 5 | **Persistent Graph Store (Neo4j)** | ✅ Done | Multi-project audit at scale |
| 6 | **Test Suite (pytest)** | ✅ Done | Quality gate before release |

---

## Module 1 · HTTP API (FastAPI)

> **Goal:** Expose the brain's public API surface via a REST API, following the suggested shape in INTEGRATION.md §5.2.

### Tasks

- [x] **1.1 — Project scaffolding** ✅
  - Add `fastapi`, `uvicorn[standard]`, `python-multipart` to `pyproject.toml` dependencies
  - Create `src/ai_testplan_generator/api/` package with `__init__.py`
  - Create `src/ai_testplan_generator/api/app.py` — FastAPI app factory
  - Create `src/ai_testplan_generator/api/deps.py` — dependency injection (Brain singleton)

- [x] **1.2 — Health & metadata endpoint** ✅
  - `GET /health` → `{"status": "ok", "version": "0.1.0"}`
  - Useful for Docker health checks and load balancer probes

- [x] **1.3 — Document ingestion endpoint** ✅
  - `POST /projects/{project_id}/ingest` — multipart file upload
  - Returns `IngestionResult` (document, sections, chunks, requirements)
  - Accepts `.pdf`, `.docx`, `.xlsx`, `.xlsm`, `.md`, `.txt`

- [x] **1.4 — Autonomous plan generation endpoint** ✅
  - `POST /projects/{project_id}/plans` — `{goal, detail_level}` body
  - Launches the autonomous pipeline as a background task
  - Returns `{session_id}` immediately (non-blocking)

- [x] **1.5 — Session status & progress endpoint** ✅
  - `GET /sessions/{session_id}` — returns current `AutonomousState` + episodic progress events
  - Allows the frontend to poll for completion

- [x] **1.6 — Plan retrieval endpoint** ✅
  - `GET /projects/{project_id}/plans/{plan_id}` — returns full `TestPlan` JSON

- [x] **1.7 — Chat / copilot endpoint** ✅
  - `POST /chat` — `{project_id, session_id, message}` body
  - Returns `ChatReply` (assistant_message, pending_action)

- [x] **1.8 — Traceability endpoint** ✅
  - `GET /trace/{artefact_id}` — returns upstream graph ancestors
  - Powers the "why does this test exist?" drill-down

---

## Module 2 · Containerisation (Docker)

- [x] **2.1 — Dockerfile** ✅
  - Multi-stage build: builder (gcc + wheel compile) → runtime (python:3.11-slim)
  - Non-root `app` user for security
  - `uvicorn` factory entrypoint

- [x] **2.2 — docker-compose.yml** ✅
  - API service with env_file injection
  - Commented-out companion services: Qdrant, Redis, Neo4j (ready to enable)

- [x] **2.3 — .dockerignore** ✅
  - 25 active rules excluding venvs, IDE files, docs, .env

- [x] **2.4 — Health check integration** ✅
  - Dockerfile `HEALTHCHECK` calls `GET /health` every 30s
  - docker-compose mirrors the same healthcheck

---

## Module 3 · Persistent Vector Store (Qdrant adapter)

- [x] **3.1 — QdrantSemanticStore** ✅
  - Implements `SemanticStore` protocol
  - Namespaces map to Qdrant collections
  - Filters translate to native `MatchValue` / `MatchAny`
  - Batched upserts (100 per batch)

- [x] **3.2 — Config wiring** ✅
  - `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_EMBEDDING_DIM` env vars
  - `MemoryManager._resolve_semantic()` auto-selects based on `SEMANTIC_MEMORY_BACKEND`
  - Lazy import: `qdrant-client` only loaded when backend is `qdrant`

- [x] **3.3 — Integration smoke test** ✅
  - Protocol satisfaction verified at runtime
  - Config defaults validated

---

## Module 4 · Persistent Episodic Store (SQLite adapter)

- [x] **4.1 — SQLiteEpisodicStore** ✅
  - Implements `EpisodicStore` protocol
  - WAL mode + NORMAL sync for performance
  - INSERT OR IGNORE for idempotency
  - LIKE-based search (FTS5 upgrade path noted)

- [x] **4.2 — Config wiring** ✅
  - `SQLITE_EPISODIC_PATH` env var added to config + .env.example
  - `MemoryManager._resolve_episodic()` auto-selects based on `EPISODIC_MEMORY_BACKEND`

- [x] **4.3 — Integration smoke test** ✅
  - Protocol satisfaction verified
  - append, recent (with kind filtering), and search all validated

---

## Module 5 · Persistent Graph Store (Neo4j adapter)

- [x] **5.1 — Neo4jGraphStore** ✅
  - Mirrors full `CrossDocumentGraph` API: 8 methods
  - Cypher-native: MERGE for idempotent writes, variable-length paths for ancestors
  - Index creation on init for performance

- [x] **5.2 — Config wiring** ✅
  - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` env vars
  - `MemoryManager._resolve_graph()` auto-selects based on `CROSSDOC_GRAPH_BACKEND`
  - Lazy import: `neo4j` driver only loaded when backend is `neo4j`

- [x] **5.3 — Integration smoke test** ✅
  - All 8 API methods verified present
  - Default fallback (NetworkX) confirmed working
  - Full app build validated with all 3 resolvers

---

## Module 6 · Test Suite (pytest)

- [x] **6.1 — Test fixtures with mocked LLMGateway** ✅
  - `MockLLMGateway` with deterministic embed vectors and call logging
  - Pre-wired `Brain` fixture with in-memory backends
  - Factory helpers for all model types (`make_document`, `make_section`, `make_chunk`, `make_requirement`, `make_test_case`)

- [x] **6.2 — Unit tests for models, ingestion, memory** ✅
  - 16 model tests (creation, JSON roundtrip, enum values, traceability)
  - 18 memory tests (working, episodic, semantic, cross-doc graph, integrated manager)

- [x] **6.3 — Integration tests for API** ✅
  - 9 API tests (health, ingestion validation, plan creation, session/plan 404s, trace)
  - Uses FastAPI TestClient with mocked Brain

- [x] **6.4 — CI configuration** ✅
  - `[tool.pytest.ini_options]` added to pyproject.toml
  - `asyncio_mode = "auto"` for zero-boilerplate async tests

> **Result: 43/43 tests passing ✅**

---

*Last updated: 2026-04-23 00:25*
