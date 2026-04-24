# Development Plan — Finalising the AI Test Plan Generator

> **Target audience:** AI coding agents (and human engineers) building
> out the remaining modules on top of the already-complete core brain.
>
> **How to use this document:** Each module is a self-contained unit of
> work. Pick one, confirm its dependencies are merged, then follow its
> **Contract → Implementation → Tests → Acceptance** sections. Do not
> deviate from the listed file paths or public interfaces — other
> modules depend on them.
>
> **Hard rules for every module:**
> 1. Use only types and interfaces declared in [INTEGRATION.md §8](INTEGRATION.md).
> 2. No breaking changes to `ai_testplan_generator.models.*`.
> 3. Every new backend implements an existing `Protocol`/ABC — do not
>    invent new ones without explicit sign-off.
> 4. Async everywhere. Never call a sync I/O function inside an async
>    handler without `asyncio.to_thread`.
> 5. Strict typing — `mypy --strict` must pass on every new file.
> 6. No emojis in code or comments.

---

## Legend

- **[P0]** — blocking for a production deploy
- **[P1]** — required for a full-feature launch
- **[P2]** — polish / operational hardening
- **Deps:** modules that MUST be merged first
- **Surface:** the public API this module exposes to callers

---

## Module Map Overview

```
Phase 1 — Persistence           M01 M02 M03 M04
Phase 2 — API Layer             M05 M06 M07 M08 M09 M10 M11
Phase 3 — Auth & Security       M12 M13 M14 M15 M16
Phase 4 — Background Jobs       M17 M18 M19
Phase 5 — Observability         M20 M21 M22 M23
Phase 6 — Frontend              M24 M25 M26 M27 M28 M29 M30
Phase 7 — Deployment            M31 M32 M33 M34
Phase 8 — Testing               M35 M36 M37 M38
```

Parallelism guide: M01–M04 can all be built in parallel. M05 unblocks
M06–M11. M13 unblocks M14–M16. M17 unblocks M18–M19. The frontend team
can start M24 as soon as M06 + M07 are stable.

---

# Phase 1 · Persistence Backends

The brain ships with in-memory reference stores. Production needs
persistent ones. All three adapters implement existing Protocols — no
caller code changes.

## M01 · Qdrant Semantic Store Adapter  **[P0]**

**Deps:** none (implements existing `SemanticStore` Protocol).
**Goal:** persist all vector embeddings (chunks, requirements,
lessons) across restarts; support multi-tenant filtering.

### Files to create
- `src/ai_testplan_generator/memory/backends/__init__.py`
- `src/ai_testplan_generator/memory/backends/qdrant_store.py`
- `tests/memory/test_qdrant_store.py`

### Contract
Implement `ai_testplan_generator.memory.base.SemanticStore`:

```python
class QdrantSemanticStore(SemanticStore):
    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        embedding_dim: int,
        collection_prefix: str = "aitpg",
    ) -> None: ...
```

### Implementation notes
- One Qdrant collection per namespace. Namespace names are already
  scoped (`chunks:general`, `chunks:{project_id}`, `requirements:{project_id}`).
  Prefix them with `collection_prefix` to share a cluster across envs:
  `aitpg_chunks_general`, `aitpg_chunks_proj-42`, etc.
- Auto-create collections on first `upsert` with distance=`Cosine` and
  `vector_size=embedding_dim`.
- Payload indexing: create payload indexes on `project_id`, `scope`,
  `document_id`, `kind` so the filter path is fast.
- Use the **async** client (`AsyncQdrantClient`).
- Batch upserts in chunks of 256 points.
- Map `filters={"project_id": "..."}` to Qdrant's `Filter` with
  `must=[FieldCondition(key="project_id", match=MatchValue(value=...))]`.

### Wiring
Add a factory helper in `memory/backends/__init__.py`:
```python
def build_semantic_store(settings: Settings) -> SemanticStore: ...
```
Update `Brain.build` (in `pipelines/brain.py`) to dispatch on
`settings.semantic_memory_backend` — `inmemory` → existing impl,
`qdrant` → new adapter. Read `settings.qdrant_url`, `settings.qdrant_api_key`,
`settings.qdrant_embedding_dim`.

### Tests
- Launch ephemeral Qdrant via `qdrant-client` in-memory mode
  (`QdrantClient(":memory:")`) or `pytest-docker`.
- Round-trip: upsert → query → verify ordering.
- Filter test: two projects, query with filter, assert isolation.
- Upsert overwrite: same id twice, assert latest payload wins.

### Acceptance
- All existing tests pass with `SEMANTIC_MEMORY_BACKEND=qdrant`.
- A 10k-chunk ingest + a retrieval round-trip completes in < 15 s on
  a local Qdrant.

---

## M02 · SQLite Episodic Store Adapter  **[P0]**

**Deps:** none (implements `EpisodicStore` Protocol).
**Goal:** persist session event logs (messages, decisions, findings)
across restarts.

### Files to create
- `src/ai_testplan_generator/memory/backends/sqlite_episodic.py`
- `src/ai_testplan_generator/memory/backends/migrations/001_episodic.sql`
- `tests/memory/test_sqlite_episodic.py`

### Contract
```python
class SqliteEpisodicStore(EpisodicStore):
    def __init__(self, *, db_path: str) -> None: ...
    async def close(self) -> None: ...
```

### Schema (migration 001)
```sql
CREATE TABLE IF NOT EXISTS episodic_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL,          -- ISO 8601 UTC
    session_id   TEXT    NOT NULL,
    actor        TEXT    NOT NULL,
    kind         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    metadata     TEXT    NOT NULL DEFAULT '{}'  -- JSON
);
CREATE INDEX IF NOT EXISTS idx_episodic_session_ts
    ON episodic_events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_episodic_session_kind
    ON episodic_events(session_id, kind);
```

### Implementation notes
- Use `aiosqlite` (add to `pyproject.toml` dependencies).
- Enable `PRAGMA journal_mode=WAL` for concurrent reads during writes.
- Run the migration on connection init — check for table existence,
  run `.sql` files in order.
- `search` is a `LIKE '%...%'` scan — acceptable for episodic size; if
  volume grows, swap for sqlite-vec or move to Postgres.
- `recent` with `kinds` filter → `WHERE kind IN (?, ?, ...)`.

### Tests
- `pytest` with `tmp_path` fixture for an isolated db file.
- Append 1000 events across 3 sessions → recent returns only target
  session, kinds filter honoured.
- Concurrent writes from multiple asyncio tasks don't corrupt.

### Acceptance
- Running the interactive pipeline twice with the same `session_id`
  retrieves history from run 1 in run 2.

---

## M03 · Neo4j Cross-Document Graph Adapter  **[P1]**

**Deps:** none (new implementation of graph surface).
**Goal:** back the traceability graph with Neo4j for multi-project
audits and fast ancestor traversal.

### Files to create
- `src/ai_testplan_generator/memory/backends/neo4j_graph.py`
- `tests/memory/test_neo4j_graph.py`

### Contract
The current `CrossDocumentGraph` is a concrete class, not a Protocol.
**First step of this module:** extract a `CrossDocumentGraphProtocol`
(runtime_checkable) covering the methods `add_node`, `add_nodes`,
`add_link`, `add_links`, `neighbours`, `coverage_matrix`, `ancestors`,
`to_dict`. Rename the current class to `InMemoryCrossDocumentGraph`
and make both implement the protocol.

Then implement:
```python
class Neo4jCrossDocumentGraph(CrossDocumentGraphProtocol):
    def __init__(self, *, uri: str, user: str, password: str,
                 database: str = "neo4j") -> None: ...
    async def close(self) -> None: ...
```

### Implementation notes
- Use the `neo4j` async driver.
- Node labels map to `node_type` ("Document", "Section", "Chunk",
  "Requirement", "TestCase", "TestPlan").
- Edge types map to `TraceKind` values.
- `coverage_matrix` → Cypher:
  ```cypher
  UNWIND $req_ids AS rid
  MATCH (tc:TestCase)-[:covers]->(r:Requirement {id: rid})
  RETURN rid, collect(tc.id) AS tc_ids
  ```
- `ancestors` with depth → `MATCH (n)-[:derives_from*1..$depth]->(a)`.

### Tests
- Use Testcontainers or a local Neo4j. Skip if not reachable.
- Same behavioural tests as the in-memory impl (reuse a test mixin).

### Acceptance
- `CROSSDOC_GRAPH_BACKEND=neo4j` passes the full autonomous pipeline
  demo.

---

## M04 · Document Blob Storage  **[P1]**

**Deps:** none.
**Goal:** store the original uploaded files separately from the
derived artefacts (chunks, requirements). Needed for re-ingest,
audit, and source quoting in the UI.

### Files to create
- `src/ai_testplan_generator/storage/__init__.py`
- `src/ai_testplan_generator/storage/base.py`     (new Protocol)
- `src/ai_testplan_generator/storage/local_fs.py`  (default impl)
- `src/ai_testplan_generator/storage/s3.py`        (optional impl)
- `tests/storage/test_local_fs.py`

### Contract
```python
class BlobStore(Protocol):
    async def put(self, key: str, data: bytes,
                  content_type: str) -> str: ...   # returns canonical URI
    async def get(self, key: str) -> bytes: ...
    async def get_stream(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def presign_get(self, key: str,
                          expires_s: int = 900) -> str | None: ...
```

### Implementation notes
- Key convention: `projects/{project_id}/docs/{sha256}/{filename}`.
- `LocalFilesystemBlobStore` writes under a configurable root
  (default `./data/blobs`). `presign_get` returns `None`.
- `S3BlobStore` (optional extra) uses `aioboto3`.
- Wire the ingestion pipeline to call `BlobStore.put` before loading,
  so the `Document.source_uri` points at the stored blob, not the
  client's upload path.

### Settings to add (config.py)
```
BLOB_STORE_BACKEND=local          # local | s3
BLOB_STORE_LOCAL_ROOT=./data/blobs
S3_BUCKET=...
S3_REGION=...
```

### Acceptance
- Ingesting a PDF writes the blob; the stored `Document.source_uri`
  round-trips through `BlobStore.get`.

---

# Phase 2 · HTTP API Layer

FastAPI has been added to dependencies. This phase makes the brain
reachable over HTTP. Each endpoint module is a FastAPI router.

## M05 · FastAPI Application Skeleton  **[P0]**

**Deps:** M01 (recommended), M02 (recommended).
**Goal:** a runnable `uvicorn` app with middleware, error handling,
health checks, lifespan management, and a Brain instance.

### Files to create
- `src/ai_testplan_generator/api/__init__.py`
- `src/ai_testplan_generator/api/app.py`
- `src/ai_testplan_generator/api/deps.py`
- `src/ai_testplan_generator/api/errors.py`
- `src/ai_testplan_generator/api/schemas/__init__.py`     # request/response wrappers
- `src/ai_testplan_generator/api/routers/__init__.py`
- `src/ai_testplan_generator/api/routers/health.py`
- `tests/api/test_app.py`

### Contract
`api.app:create_app() -> FastAPI` is the application factory. Uvicorn
entry point: `uvicorn ai_testplan_generator.api.app:create_app --factory`.

### Implementation notes
- **Lifespan:** build a single `Brain` at app startup (async lifespan),
  close backends on shutdown.
- **Middleware:** `CORSMiddleware`, request-id injection (pass through
  to `structlog.contextvars`), request timing.
- **Global exception handler:** return JSON `{detail, request_id, error_code}`
  for our error types (see `errors.py`). Never leak stack traces in
  production.
- **`api/errors.py`** defines typed exceptions:
  `NotFoundError`, `ValidationError`, `AuthError`, `ConflictError`,
  `RateLimitError`, `BackendUnavailable`.
- **`api/deps.py`** exports `get_brain()` / `get_settings()` FastAPI
  dependencies reading from `app.state`.
- **Health endpoints** (from `routers/health.py`):
  - `GET /healthz` — returns 200 immediately (liveness)
  - `GET /readyz` — checks LLM gateway reachability + each configured
    backend; returns 503 if any is down (readiness)
- **OpenAPI:** title, version, description from `settings`.

### Acceptance
- `uvicorn ... --factory` starts cleanly.
- `GET /healthz` returns 200.
- `GET /readyz` returns 503 with a precise body when Qdrant is down.

---

## M06 · Document Ingestion Endpoints  **[P0]**

**Deps:** M05, M04 (blob store).

### Files to create
- `src/ai_testplan_generator/api/routers/documents.py`
- `src/ai_testplan_generator/api/schemas/documents.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/projects/{project_id}/documents` | Upload file (multipart) — streams to blob store, triggers ingest |
| `GET`  | `/projects/{project_id}/documents` | List documents with pagination |
| `GET`  | `/projects/{project_id}/documents/{doc_id}` | Get single doc metadata |
| `GET`  | `/projects/{project_id}/documents/{doc_id}/download` | Presigned / streamed download |
| `DELETE` | `/projects/{project_id}/documents/{doc_id}` | Remove doc + derived chunks/requirements |
| `POST` | `/general/documents` | Upload to general (cross-project) KB |

### Implementation notes
- Upload request: `multipart/form-data` with `file` (UploadFile).
  Max body size from settings. Reject unsupported extensions early
  using `_EXT_MAP`.
- **Stream to blob** in chunks (`file.read(1<<20)` loop) so large PDFs
  don't buffer fully in memory.
- Ingest is **synchronous for small docs, backgrounded for large ones.**
  Rule of thumb: if file size > 5 MB, enqueue a background job
  (M17) and return `202 Accepted` with a `job_id`.
- Response schema (sync case):
  ```json
  {
    "document": Document,
    "n_sections": int,
    "n_chunks": int,
    "n_requirements": int
  }
  ```
- Deletion cascades: remove chunks from semantic store, remove
  requirements, remove graph nodes + edges.

### Acceptance
- POSTing a 2-page PDF returns 200 with counts.
- POSTing a 500-page PDF returns 202 with a job_id.
- DELETE removes all traces (assert via a follow-up retrieval that
  returns zero hits).

---

## M07 · Test Plan Generation Endpoints  **[P0]**

**Deps:** M05, M17 (jobs).

### Files to create
- `src/ai_testplan_generator/api/routers/plans.py`
- `src/ai_testplan_generator/api/schemas/plans.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/projects/{project_id}/plans` | Start autonomous run → 202 + job_id + session_id |
| `GET`  | `/projects/{project_id}/plans` | List plans (summary only) |
| `GET`  | `/projects/{project_id}/plans/{plan_id}` | Full `TestPlan` JSON |
| `GET`  | `/projects/{project_id}/plans/{plan_id}?detail=summary` | Summary-level projection |
| `GET`  | `/projects/{project_id}/plans/{plan_id}/export.json` | Download |
| `GET`  | `/projects/{project_id}/plans/{plan_id}/coverage` | Coverage matrix only |
| `DELETE` | `/projects/{project_id}/plans/{plan_id}` | Remove plan |

### Request body (POST)
```json
{
  "goal": "Qualify the pump controller against SRS v3 and ISO 4413.",
  "detail_level": "detailed",
  "max_revision_rounds": 3
}
```

### Implementation notes
- Always runs as a background job (autonomous runs take minutes).
- Persist the final `TestPlan` in a small plans table (add to SQLite
  migration) or S3 JSON file. **Minimum implementation:** write
  `plan.model_dump_json()` to `BlobStore` under
  `projects/{id}/plans/{plan_id}.json`.
- Summary projection: hide `steps` and `acceptance_criteria` from
  each `TestCase`.

### Acceptance
- Full round-trip: upload docs → POST plan → poll job → fetch plan
  JSON → coverage matrix non-empty.

---

## M08 · Chat / Copilot Endpoints  **[P0]**

**Deps:** M05.

### Files to create
- `src/ai_testplan_generator/api/routers/chat.py`
- `src/ai_testplan_generator/api/schemas/chat.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/chat` | Send one turn → `ChatReply` |
| `GET`  | `/chat/{session_id}/history` | Episodic history for a session |
| `POST` | `/chat/{session_id}/confirm` | Confirm a pending mutation (ties to `CopilotReply.pending_action`) |
| `WS`   | `/chat/{session_id}/stream` | WebSocket for streaming tokens |

### Request body (POST /chat)
```json
{
  "session_id": "chat_abc",       // optional — server generates if absent
  "project_id": "proj-42",        // optional for general queries
  "message": "What standards are referenced?"
}
```

### Implementation notes
- Non-streaming endpoint wraps `InteractivePipeline.session(...).ask(msg)`.
- Streaming endpoint: open the gateway's `stream()` directly and forward
  tokens. Still log the final turn to episodic memory when the stream
  ends.
- History endpoint: `brain.memory.episodic.recent(session_id, limit=...)`.

### Acceptance
- Two successive POSTs with the same `session_id` show continuity
  (the copilot references the first message in the second reply).

---

## M09 · Traceability Endpoints  **[P1]**

**Deps:** M05.

### Files to create
- `src/ai_testplan_generator/api/routers/traceability.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/trace/{artefact_id}` | Full lineage (ancestors + descendants up to depth) |
| `GET` | `/trace/{artefact_id}/ancestors?depth=3` | Upstream only |
| `GET` | `/projects/{project_id}/coverage` | Full project coverage matrix |
| `GET` | `/projects/{project_id}/gaps` | Requirements with zero covering test cases |

### Response shape
```json
{
  "root": {"id": "tc_81c0", "type": "TestCase", "title": "..."},
  "edges": [
    {"from": "tc_81c0", "to": "req_7f2a", "kind": "covers", "confidence": 1.0},
    ...
  ],
  "nodes": { "req_7f2a": {...Requirement}, "ch_a3b9": {...Chunk} }
}
```

### Acceptance
- `/trace/{tc_id}/ancestors?depth=3` returns the chain test → req →
  chunk → section → document.

---

## M10 · Projects & Users Endpoints  **[P0]**

**Deps:** M05, M13 (auth).

### Files to create
- `src/ai_testplan_generator/api/routers/projects.py`
- `src/ai_testplan_generator/domain/projects.py`    (new — lightweight repo)
- `src/ai_testplan_generator/domain/users.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/projects` | Create project (name, description, owner) |
| `GET`  | `/projects` | List projects visible to the caller |
| `GET`  | `/projects/{id}` | Get project metadata |
| `PATCH`| `/projects/{id}` | Update name/description |
| `DELETE`| `/projects/{id}` | Archive (soft delete) |
| `POST` | `/projects/{id}/members` | Invite user with role |
| `DELETE`| `/projects/{id}/members/{user_id}` | Remove member |

### Data model
`Project(id, name, description, owner_id, created_at, archived_at)`.
Store in SQLite (extend migrations). Members table:
`ProjectMember(project_id, user_id, role, added_at)`.

Roles: `owner`, `editor`, `reviewer`, `viewer` — used by M14.

### Acceptance
- Creating a project returns a stable id usable in document / plan
  endpoints.

---

## M11 · Progress Streaming (SSE)  **[P1]**

**Deps:** M05, M17, M18.

### Files to create
- `src/ai_testplan_generator/api/routers/events.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/sessions/{session_id}/events` | SSE stream of agent events |
| `GET` | `/jobs/{job_id}` | Current job status snapshot |

### Implementation notes
- SSE via `sse-starlette` (add dep).
- Subscribe to the event broker (M18) filtered by `session_id`.
- Emit events for each `agent_start` / `agent_done` / `agent_error`
  + completion events from the job runner.
- Event payload:
  ```json
  event: agent_progress
  data: {"ts": "...", "actor": "generator", "kind": "agent_done",
         "content": "generator returned", "metadata": {...}}
  ```

### Acceptance
- Running the autonomous pipeline while a client is subscribed yields
  ~20 events in order.

---

# Phase 3 · Authentication & Security

Cahier des charges §10: API Cloud chiffrées, gestion des droits d'accès
par rôle, traçabilité et confidentialité.

## M12 · User Identity Model  **[P0]**

**Deps:** none.

### Files to create
- `src/ai_testplan_generator/domain/users.py`        (extended)
- `src/ai_testplan_generator/domain/auth.py`
- `src/ai_testplan_generator/memory/backends/migrations/002_users.sql`

### Schema
```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,        -- usr_<hex>
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL,
    password_hash   TEXT,                    -- NULL if SSO-only
    created_at      TEXT NOT NULL,
    disabled_at     TEXT
);
CREATE TABLE api_keys (
    id              TEXT PRIMARY KEY,        -- key_<hex>
    user_id         TEXT NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,
    hash            TEXT NOT NULL,           -- bcrypt of key material
    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    revoked_at      TEXT
);
```

### Acceptance
- CRUD via repo: create user, disable user, rotate api key.

---

## M13 · Authentication (JWT + API Key)  **[P0]**

**Deps:** M05, M12.

### Files to create
- `src/ai_testplan_generator/api/security/jwt.py`
- `src/ai_testplan_generator/api/security/api_key.py`
- `src/ai_testplan_generator/api/security/password.py`
- `src/ai_testplan_generator/api/routers/auth.py`

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/login` | email + password → JWT (access + refresh) |
| `POST` | `/auth/refresh` | refresh → new access token |
| `POST` | `/auth/logout` | revoke refresh |
| `POST` | `/auth/api-keys` | create key for caller |
| `GET`  | `/auth/api-keys` | list keys |
| `DELETE`| `/auth/api-keys/{id}` | revoke |
| `GET`  | `/auth/me` | current user |

### Implementation notes
- JWT library: `pyjwt`. Algorithm: `RS256` (support key rotation).
  Keys read from settings (`JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`).
  Fall back to `HS256` + `JWT_SECRET` for local dev only.
- Access token TTL: 15 min. Refresh TTL: 14 days. Both carry `sub`,
  `iat`, `exp`, `scope`.
- Password hashing: `argon2-cffi` (add dep). Never bcrypt plaintext
  passwords.
- API key: random 32 bytes, base64url. Store only the bcrypt hash;
  verify by hashing the presented key.
- Auth dep: `get_current_user` supports both Bearer JWT and
  `X-Api-Key` headers.

### Acceptance
- Hitting a protected endpoint without credentials returns 401.
- With a valid token, the endpoint resolves `current_user` correctly.

---

## M14 · RBAC Middleware  **[P0]**

**Deps:** M10, M13.

### Files to create
- `src/ai_testplan_generator/api/security/rbac.py`

### Model
Project-scoped roles (`owner`, `editor`, `reviewer`, `viewer`) +
global role (`admin`).

Permissions table (in code, not DB):
```python
PERMISSIONS = {
    "project.read":    {"owner", "editor", "reviewer", "viewer"},
    "project.write":   {"owner", "editor"},
    "project.admin":   {"owner"},
    "document.upload": {"owner", "editor"},
    "document.delete": {"owner", "editor"},
    "plan.generate":   {"owner", "editor"},
    "plan.read":       {"owner", "editor", "reviewer", "viewer"},
    "plan.approve":    {"owner", "reviewer"},
    "general_kb.write":{"admin"},    # global KB is admin-only
}
```

### Usage
```python
@router.post("/projects/{project_id}/plans",
             dependencies=[Depends(require("plan.generate"))])
async def create_plan(...): ...
```

`require(permission)` resolves the caller's role in the project_id
from path params and raises 403 if not permitted.

### Acceptance
- A `viewer` cannot POST documents; gets 403.
- An `admin` can write to `/general/documents`.

---

## M15 · Audit Logging  **[P1]**

**Deps:** M05, M12.

### Files to create
- `src/ai_testplan_generator/api/middleware/audit.py`
- `src/ai_testplan_generator/memory/backends/migrations/003_audit.sql`

### Schema
```sql
CREATE TABLE audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    user_id      TEXT,
    project_id   TEXT,
    action       TEXT NOT NULL,      -- "plan.generate", "document.delete", etc.
    target_type  TEXT,
    target_id    TEXT,
    status       INTEGER NOT NULL,   -- HTTP status
    ip           TEXT,
    user_agent   TEXT,
    metadata     TEXT DEFAULT '{}'
);
CREATE INDEX idx_audit_user_ts ON audit_events(user_id, ts);
CREATE INDEX idx_audit_action_ts ON audit_events(action, ts);
```

### Implementation notes
- Write on every mutating request (POST/PATCH/DELETE).
- Don't block the response on audit write — use a fire-and-forget
  async task but surface failures to logs.

### Acceptance
- Every mutation appears in `audit_events` within 1 s.

---

## M16 · Secrets & Encryption-at-Rest  **[P1]**

**Deps:** M04.

### Scope
- Envelope-encrypt blob store contents with a KEK from env
  (`BLOB_ENCRYPTION_KEY`, base64 32 bytes).
- Use `cryptography.fernet` for simplicity; upgrade path to KMS later.
- Document rotation: re-encrypt keyed by `kek_version` stored alongside
  each blob.

### Acceptance
- Blobs on disk are not readable with standard tools; the API can
  still decrypt and serve them.

---

# Phase 4 · Background Job Processing

## M17 · Task Queue (ARQ / Redis)  **[P0]**

**Deps:** M05.

### Files to create
- `src/ai_testplan_generator/jobs/__init__.py`
- `src/ai_testplan_generator/jobs/queue.py`
- `src/ai_testplan_generator/jobs/worker.py`
- `src/ai_testplan_generator/jobs/tasks/ingest.py`
- `src/ai_testplan_generator/jobs/tasks/autonomous.py`

### Why ARQ
Python-native, Redis-backed, async-first. Simpler than Celery. Has
cron-like scheduling for future cleanup jobs.

### Tasks
| Task | Args | Side effect |
|---|---|---|
| `ingest_document` | `blob_key, project_id, scope` | IngestionPipeline.ingest_file |
| `run_autonomous`  | `project_id, goal, detail_level, session_id` | AutonomousPipeline.run |
| `delete_project_artefacts` | `project_id` | cascade delete from all backends |

### Job state API (exposed via M11 `GET /jobs/{job_id}`)
- `queued`, `in_progress`, `succeeded`, `failed`
- `result` (on success): JSON (e.g. `plan_id`)
- `error` (on failure): short string + correlation id

### Retry policy
Transient LLM / network errors: 3 retries with exponential backoff.
Validation errors: no retry.

### Settings to add
```
REDIS_URL=redis://localhost:6379/0
JOB_WORKER_CONCURRENCY=4
```

### Acceptance
- Triggering `/projects/{id}/plans` returns a job_id immediately;
  polling shows `in_progress` → `succeeded` with `result.plan_id`.

---

## M18 · Event Broker (Redis Pub/Sub)  **[P1]**

**Deps:** M17.

### Files to create
- `src/ai_testplan_generator/events/__init__.py`
- `src/ai_testplan_generator/events/broker.py`

### Contract
```python
class EventBroker(Protocol):
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...
```

Topics: `session:{session_id}`, `job:{job_id}`, `project:{id}`.

### Integration
Modify `BaseAgent.invoke` (or wrap it) to publish to
`session:{session_id}` on every start/done/error event — in addition
to persisting episodically.

### Acceptance
- An SSE subscriber gets ~20 events in real time during an autonomous
  run.

---

## M19 · Dead-Letter & Retry Dashboard Data  **[P2]**

**Deps:** M17.

### Scope
- Move permanently-failed jobs to a `jobs_deadletter` list.
- `GET /admin/jobs/deadletter` (admin only) to inspect and requeue.
- Counters exposed to Prometheus (see M21).

---

# Phase 5 · Observability

## M20 · OpenTelemetry Instrumentation  **[P1]**

**Deps:** M05.

### Files to create
- `src/ai_testplan_generator/telemetry/__init__.py`
- `src/ai_testplan_generator/telemetry/otel.py`

### Scope
- `init_tracing(service_name, exporter_url)` using `opentelemetry-sdk`.
- Auto-instrument FastAPI + httpx + aiosqlite + redis.
- Manual spans around every `BaseAgent.invoke` (wrap it once in
  `base.py`). Span attributes: `agent.name`, `session_id`, `project_id`,
  `llm.model`, `llm.input_tokens`, `llm.output_tokens`.
- LLM calls: span per `gateway.complete`, child of the agent span.

### Settings
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=aitpg-api
OTEL_RESOURCE_ATTRIBUTES=env=dev
```

### Acceptance
- A full autonomous run produces a coherent trace in Jaeger / Tempo
  showing orchestrator → agents → LLM calls with timing.

---

## M21 · Prometheus Metrics  **[P1]**

**Deps:** M05.

### Files to create
- `src/ai_testplan_generator/telemetry/metrics.py`
- New endpoint: `GET /metrics`

### Metrics (names, types)
```
aitpg_requests_total{method,path,status}           counter
aitpg_request_duration_seconds{method,path}        histogram
aitpg_llm_calls_total{model,role,outcome}          counter
aitpg_llm_tokens_total{model,role,direction}       counter
aitpg_llm_latency_seconds{model,role}              histogram
aitpg_agent_runs_total{agent,outcome}              counter
aitpg_agent_duration_seconds{agent}                histogram
aitpg_ingest_docs_total{kind,outcome}              counter
aitpg_ingest_chunks_total                          counter
aitpg_job_queue_depth{task}                        gauge
aitpg_job_duration_seconds{task,outcome}           histogram
```

### Acceptance
- `/metrics` returns Prometheus-format output. Grafana dashboard JSON
  ships in `ops/grafana/dashboards/` (see M33).

---

## M22 · Structured Log Shipping  **[P2]**

**Deps:** M05.

### Scope
- Configure `structlog` JSON renderer when `LOG_FORMAT=json`.
- Include `trace_id`, `span_id`, `request_id`, `user_id`, `project_id`
  as contextvars on every log line.
- Human-readable renderer for local dev.

---

## M23 · Cost Tracking Aggregator  **[P1]**

**Deps:** M17, M21.

### Files to create
- `src/ai_testplan_generator/telemetry/cost.py`

### Scope
- Per-request: capture `LLMResponse.input_tokens` + `output_tokens` +
  `model`; compute cost using a `COST_TABLE` dict (populated from
  `pyproject.toml` extras or a YAML file shipped alongside).
- Per-session aggregate: write to a new `llm_usage` table keyed by
  session + project + user.
- Admin endpoint: `GET /admin/costs?from=...&to=...&group_by=project`.

### Acceptance
- Running an autonomous pipeline produces a non-zero cost entry
  tagged with the right project.

---

# Phase 6 · Frontend

## M24 · Frontend Stack & Scaffold  **[P0]**

**Deps:** M05.

### Stack decision (recorded here so other FE modules follow)
- **Framework:** React 18 + Vite.
- **Language:** TypeScript strict mode.
- **Styling:** Tailwind + shadcn/ui (accessible primitives).
- **Data fetching:** TanStack Query (cache, suspense).
- **State:** TanStack Query for server state; Zustand for ephemeral UI.
- **Routing:** TanStack Router.
- **Forms:** react-hook-form + Zod.
- **API client:** auto-generated from the FastAPI OpenAPI schema via
  `openapi-typescript-codegen`. Regenerate in CI.
- **Graph viz:** Cytoscape.js for traceability; Mermaid.js for
  architecture.
- **Gantt:** `frappe-gantt` or `react-gantt-task`.

### Repo layout
```
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  src/
    main.tsx
    app/                 # router + layout
    features/
      documents/
      plans/
      chat/
      traceability/
      projects/
      auth/
    lib/
      api/               # generated client
      auth/
      query/             # TanStack setup
    components/ui/       # shadcn
    components/charts/
```

### Acceptance
- `npm run dev` shows a login page wired to `/auth/login`.
- OpenAPI regen script is `npm run gen:api` and is in CI.

---

## M25 · Documents UI  **[P0]**

**Deps:** M24, M06.

### Screens
- **Project documents list:** table with kind, size, ingested_at,
  `n_chunks`, `n_requirements`.
- **Upload drawer:** drag-and-drop, progress bar using server SSE
  (M11), cancel upload.
- **Document detail:** PDF preview (pdf.js), sections tree, jump-to-
  chunk.

### Acceptance
- Uploading a PDF shows live progress and appears in the list when
  ingestion completes.

---

## M26 · Plan Viewer + Detail-Level Toggle  **[P0]**

**Deps:** M24, M07.

### Screens
- **Plan list:** filterable by status, date.
- **Plan detail:**
  - Header (scope, strategy, entry/exit criteria).
  - Top toggle **Résumé / Détaillé** → switches projection.
  - Test case table; row expand shows steps + criteria.
  - Side panel: coverage matrix (requirement → [test case ids]).
  - Export: JSON, PDF (server-rendered via `weasyprint` or similar —
    track as M26.1 subtask).

### Acceptance
- Toggling detail level is < 200 ms (uses cached server projection).
- Export PDF matches the on-screen content.

---

## M27 · Interactive Copilot UI  **[P0]**

**Deps:** M24, M08.

### Screens
- Chat column with streaming token display (WebSocket).
- Citations rendered as clickable chips opening the source doc at the
  cited page.
- Pending-action banner when `reply.pending_action !== null`; buttons
  "Confirm" / "Discard".
- Slash commands: `/plan`, `/coverage`, `/source <req_id>`.

### Acceptance
- Asking a question with citations renders chips that jump to the
  right page.

---

## M28 · Traceability Drill-Down  **[P1]**

**Deps:** M24, M09.

### Screens
- Cytoscape graph centred on a starting artefact.
- Depth slider (1–5).
- Edge filters by `TraceKind`.
- Node click → side panel with the artefact.
- "Explain this link" button → asks the copilot to narrate.

### Acceptance
- Double-clicking a node re-centres the graph on it and refetches.

---

## M29 · Gantt / Schedule Viewer  **[P1]**

**Deps:** M24, M07.

### Screens
- Gantt: one row per `TestCase`, coloured by service/resource.
- Milestones as diamonds.
- Drag to reschedule → PATCH endpoint (requires M07 extension).
- Resource load chart.

### Acceptance
- Rescheduling a test case updates backend; conflict warnings shown
  inline.

---

## M30 · Admin / Projects & Members  **[P1]**

**Deps:** M24, M10, M14.

### Screens
- Projects list with role column.
- Project create / edit.
- Members panel: invite by email, role selector, remove.
- API keys management.
- Audit log viewer (filterable).

---

# Phase 7 · Deployment

## M31 · API Dockerfile  **[P0]**

**Deps:** none (code-level).

### Files to create
- `Dockerfile`
- `.dockerignore`

### Dockerfile contents (exact)
```dockerfile
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md* ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install . && pip install "uvicorn[standard]"

FROM base AS runtime
RUN useradd --uid 10001 --create-home aitpg
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app
USER aitpg
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s CMD \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1
CMD ["uvicorn", "ai_testplan_generator.api.app:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

### Acceptance
- Image builds under 600 MB.
- Container starts in < 5 s to `GET /healthz` 200.

---

## M32 · docker-compose Dev Stack  **[P0]**

**Deps:** M31.

### Files to create
- `docker-compose.yml`
- `ops/compose/env.example`

### Services
- `api` — built from Dockerfile; depends_on redis, qdrant, neo4j.
- `worker` — same image, `CMD` overridden to run the ARQ worker.
- `redis` — official image (jobs + events).
- `qdrant` — official image.
- `neo4j` — official image.
- `prometheus` + `grafana` (profile: `observability`).
- `jaeger` (profile: `observability`).

Volumes: named volumes per stateful service, plus `./data` bind for
local blob store.

### Acceptance
- `docker compose up` → all services healthy, API reachable on :8000.

---

## M33 · Kubernetes / Helm  **[P1]**

**Deps:** M31.

### Files to create
- `ops/helm/aitpg/Chart.yaml`
- `ops/helm/aitpg/values.yaml`
- `ops/helm/aitpg/templates/{deployment-api,deployment-worker,service,ingress,configmap,secret,pdb,hpa}.yaml`
- `ops/grafana/dashboards/api.json`
- `ops/grafana/dashboards/brain.json`

### Notes
- Use a single deployment for API + a separate one for workers.
- HPA on CPU for API, on queue depth for workers (needs custom
  metric from M21).
- Pod security: non-root, read-only rootfs, `allowPrivilegeEscalation: false`.
- Secrets via K8s Secret or external-secrets operator.

### Acceptance
- `helm install aitpg ops/helm/aitpg` on a local cluster stands up a
  working stack.

---

## M34 · CI/CD Pipeline  **[P0]**

**Deps:** M35.

### Files to create
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

### CI jobs
1. `lint` — `ruff check src tests`
2. `typecheck` — `mypy --strict src`
3. `test` — `pytest` with coverage (fail under 75 %)
4. `build-frontend` — `npm ci && npm run build`
5. `build-image` — `docker build .` — push to GHCR on main
6. `helm-lint` — `helm lint ops/helm/aitpg`

### Release job (on tag)
- Build + push versioned image.
- Package + push Helm chart.
- Generate changelog from PR titles.

---

# Phase 8 · Testing

## M35 · Unit Test Suite (Core Brain)  **[P0]**

**Deps:** none.

### Files to create
```
tests/
  conftest.py
  llm/test_litellm_gateway.py
  ingestion/test_loaders.py
  ingestion/test_chunking.py
  ingestion/test_extraction.py
  memory/test_working.py
  memory/test_episodic.py
  memory/test_semantic.py
  memory/test_cross_document.py
  memory/test_manager.py
  agents/test_base.py
  agents/test_orchestrator.py
  agents/test_test_generator.py
  graphs/test_autonomous.py
  graphs/test_interactive.py
  pipelines/test_brain.py
  pipelines/test_autonomous.py
  pipelines/test_interactive.py
```

### Shared fixtures (`conftest.py`)
- `fake_llm`: an in-memory `LLMGateway` implementation returning
  deterministic canned responses + recorded calls. **This is the
  single most important fixture.** Use it everywhere; never hit a
  real provider in unit tests.
- `in_memory_brain`: a `Brain` with all four reference backends.
- `sample_document`, `sample_chunks`, `sample_requirements` factories.

### Coverage targets
- `memory/` — 95 %
- `ingestion/` — 90 % (excluding optional loader deps)
- `agents/` — 85 %
- `graphs/` — 75 %
- `pipelines/` — 80 %

### Acceptance
- `pytest` green with overall coverage ≥ 80 %.

---

## M36 · Integration Tests (API + Backends)  **[P1]**

**Deps:** M05–M11, M35.

### Scope
- Spin up Qdrant + Redis + SQLite in Testcontainers.
- End-to-end: login → create project → upload doc → generate plan →
  fetch plan → chat about it → coverage.

### Acceptance
- Runs in CI under 10 minutes.

---

## M37 · E2E Tests (Frontend)  **[P1]**

**Deps:** M24–M30.

### Scope
- Playwright. Runs against `docker compose up` stack.
- Smoke: login → upload PDF → see processed doc → generate plan →
  toggle detail → chat.

### Acceptance
- Runs on every PR touching `frontend/` or the API routers.

---

## M38 · Load Tests  **[P2]**

**Deps:** full stack.

### Scope
- Locust scenarios:
  - 50 concurrent chat sessions.
  - 10 autonomous runs on a 200-page document each.
- Measure: p95 latency, error rate, LLM cost per run.

### Acceptance
- Baseline numbers committed to `ops/perf/baseline.md` for future
  regression comparison.

---

# Cross-cutting Conventions

### Git hygiene
- Branch per module: `feat/m07-plans-api`, `feat/m14-rbac`, ...
- Conventional Commits: `feat(api): add /projects/{id}/plans endpoint (M07)`.
- One PR per module unless trivially small; link the module id in the
  PR title.

### Code style
- `ruff` + `mypy --strict` clean before review.
- Tests required alongside the module — no "I'll add tests later".
- Docstrings: brief, on module level only; avoid function-level
  docstrings that just restate the signature.

### Prompt discipline (for AI agents building these modules)
- Read the target file(s) before editing.
- Never rename existing symbols unless the module explicitly says to.
- When a module says "modify X", diff the current content; don't
  rewrite wholesale.
- Trust the existing interfaces in `models/`, `llm/base.py`,
  `memory/base.py`, `agents/base.py` — they are stable.
- If a detail is missing from this plan, pick the simplest option and
  note the assumption in the PR description.

### Configuration additions
Every new env var goes in **both** `config.py` and `.env.example`
with a comment explaining when it's read.

### Documentation duty
Every merged module updates:
- `INTEGRATION.md` §6 (move the module from "Not built" to "Done").
- `INTEGRATION.md` §8 (add new invariants if any).

---

# Recommended Build Order

If only one agent is working:

```
M35 (core tests, to catch regressions)
 → M01 (Qdrant)        ─┐
 → M02 (SQLite)         ├─ parallel
 → M04 (Blob)          ─┘
 → M05 (FastAPI skel)
 → M12 (User model) → M13 (Auth) → M14 (RBAC)
 → M10 (Projects)
 → M17 (Jobs) → M18 (Events)
 → M06, M07, M08, M11   ── parallel
 → M20, M21             ── parallel
 → M24 (FE scaffold) → M25, M26, M27 in parallel
 → M31 → M32 → M34 (CI)
 → M28, M29, M30, M36, M37, M38
 → M03, M15, M16, M19, M22, M23, M33 (polish)
```

If a team of agents splits the work, use the dependency arrows in
each module to parallelise safely.

---

# Definition of Done for the Whole Platform

A merged platform satisfies the cahier des charges when:

- All **[P0]** modules merged + green on CI.
- A fresh engineer can:
  1. `docker compose up`,
  2. log in via the UI,
  3. create a project,
  4. upload a 500-page PDF,
  5. generate a detailed test plan,
  6. chat with the copilot about it,
  7. drill down any test to its source page,
  8. view the Gantt schedule,
  9. export the plan as JSON and PDF.
- All of the above with one env var flip, swap the LLM provider from
  Anthropic to OpenAI to a local Ollama model — no redeploy.
- Traceability chain is audit-complete: every test resolves to an exact
  byte range in a source document.

That's the finish line. Build toward it.
