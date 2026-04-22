# Integration Guide

> **Audience:** engineers building the layers *around* the AI brain —
> frontend, REST/GraphQL API, containerisation, observability, auth,
> and extension modules (new loaders, new memory backends, new agents).
>
> **What this repo is:** the provider-agnostic, multi-agent intelligence
> engine. It ingests documents, extracts requirements, generates and
> reviews test plans, and runs either autonomously or as a chatbot
> copilot. It does **not** ship a UI, HTTP API, auth, or container
> definitions — those are explicitly out of scope for this iteration.

---

## 1 · Repo map at a glance

```
src/ai_testplan_generator/
  config.py             ← Settings (pydantic-settings). Single knob-box.
  models/               ← Pydantic data contracts (stable public API).
  llm/                  ← LLMGateway Protocol + LiteLLM implementation.
  ingestion/            ← Streaming loaders, hierarchical chunker, extractor.
  memory/               ← 4-tier memory (working, episodic, semantic, graph).
  knowledge/            ← General KB + Project KB wrappers.
  prompts/              ← All system prompts, centralised.
  agents/               ← 9 typed agents (analyst, extractor, architect, ...).
  graphs/               ← LangGraph state machines (autonomous + interactive).
  pipelines/            ← Brain + AutonomousPipeline + InteractivePipeline.
examples/               ← Runnable demos.
```

**Two stable entry points** for anyone wrapping the brain:

```python
from ai_testplan_generator import Brain, AutonomousPipeline, InteractivePipeline
```

Everything else is internal — you *can* reach it, but it's more likely
to churn between iterations. Stick to `Brain`, the two pipelines, and
the model classes.

---

## 2 · Public API surface — what to call

### 2.1 Construct the brain once per process

```python
from ai_testplan_generator import Brain

brain = Brain.build()          # reads env vars, uses in-memory backends
```

`Brain` is a cheap composition root. It bundles:
- the `LLMGateway` (LiteLLM-backed),
- the `MemoryManager` (4 tiers, in-memory reference impls),
- the `IngestionPipeline`,
- the `GeneralKnowledgeBase`,
- a factory `brain.project_kb(project_id)` for per-project KBs.

In production you will inject persistent backends — see §6.

### 2.2 Ingest documents

```python
kb = brain.project_kb("proj-42")
result = await kb.ingest("/path/to/spec.pdf")
# result.document, result.sections, result.chunks, result.requirements
```

Accepted formats: `.pdf`, `.docx`, `.xlsx`, `.xlsm`, `.md`, `.txt`.
The loader streams — a 10 000-page PDF does **not** materialise in RAM.

For the cross-project reference corpus (ISO standards, internal
playbooks, lessons-learnt), use `brain.general_kb.ingest(...)` instead.
Note: general KB ingests do **not** extract requirements by default
(those are reference material, not project-owned statements).

### 2.3 Run autonomously

```python
from ai_testplan_generator import AutonomousPipeline
from ai_testplan_generator.models import DetailLevel

pipeline = AutonomousPipeline(brain)
result = await pipeline.run(
    project_id="proj-42",
    goal="Qualify the pump controller against SRS v3 and ISO 4413.",
    detail_level=DetailLevel.DETAILED,   # or DetailLevel.SUMMARY
    max_revision_rounds=3,
)
# result.plan, result.schedule, result.state, result.session_id
```

`result.plan` is a `TestPlan` (see §3). Serialise with
`plan.model_dump_json(indent=2)` for the wire or the DB.

### 2.4 Run interactively (copilot)

```python
from ai_testplan_generator import InteractivePipeline

chat = InteractivePipeline(brain)
session = chat.session(project_id="proj-42")   # or pass session_id= to resume

reply = await session.ask("What standards are referenced in the corpus?")
# reply.assistant_message  -> str
# reply.pending_action     -> None | "add_test_case" | "revise_test_case" | ...
```

Sessions are keyed by `session_id`. The same session_id across calls
reuses conversation history via episodic memory.

---

## 3 · Data contracts — what you get back

All artefacts are Pydantic v2 models in `ai_testplan_generator.models`.
They are **stable** — any breaking change bumps the package major.

| Model | Purpose | Key fields |
|---|---|---|
| `Document` | Ingested source file | `id`, `title`, `kind`, `sha256`, `scope`, `project_id` |
| `Section` | Hierarchical slice of a document | `id`, `document_id`, `number`, `title`, `level`, `page_start/end` |
| `Chunk` | Retrieval-sized unit | `id`, `document_id`, `section_id`, `text`, `token_count`, `page_start/end` |
| `Requirement` | Testable normative statement | `id`, `kind`, `statement`, `priority`, `source_chunk_ids`, `verbatim_excerpt` |
| `TestCase` | Executable test | `id`, `title`, `steps[]`, `acceptance_criteria[]`, `requirement_ids[]`, `risk_level`, `estimated_duration_minutes` |
| `TestPlan` | Top-level deliverable | `id`, `title`, `detail_level`, `scope`, `strategy`, `test_cases[]`, `coverage_matrix` |
| `TraceLink` | Typed edge in the graph | `kind`, `source_id/type`, `target_id/type`, `confidence` |
| `TestSchedule` | Gantt-ready schedule | `milestones[]`, `assignments: dict[test_case_id → ScheduledAssignment]` |

All models JSON-serialise cleanly for the API wire format:

```python
plan.model_dump()          # → dict
plan.model_dump_json()     # → str
TestPlan.model_validate_json(wire_bytes)   # ← deserialise
```

Rule of thumb for the API layer: **pass these models straight through
to the client**. They were designed to be the wire format too. No DTOs,
no mapper layer.

---

## 4 · Configuration — environment variables

All configuration lives in [.env.example](.env.example). Copy it to `.env`
for local dev; surface the same vars through your container secrets in
production.

### 4.1 LLM routing (provider-agnostic via LiteLLM)

| Var | Purpose | Example values |
|---|---|---|
| `LLM_MODEL_SMART` | Reasoning tier (orchestrator, architect, reviewer) | `claude-opus-4-1-20250805`, `gpt-5`, `vertex_ai/gemini-2.5-pro` |
| `LLM_MODEL_BALANCED` | Worker tier (generator, traceability, planner, copilot) | `claude-sonnet-4-5-20250929`, `gpt-5-mini` |
| `LLM_MODEL_FAST` | Router/classifier tier (extractor, fast orchestrator branches) | `claude-haiku-4-5-20251001`, `gemini-2.5-flash` |
| `LLM_MODEL_EMBEDDING` | Vector embeddings | `text-embedding-3-large`, `voyage-3-large` |

Plus one provider credential per provider you actually route to:
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`,
`VERTEXAI_PROJECT`, `AWS_REGION_NAME`, ...

**Key property:** changing a model is a restart, not a release.

### 4.2 Runtime knobs

| Var | Default | Notes |
|---|---|---|
| `LLM_DEFAULT_TEMPERATURE` | `0.1` | Low by default — we want determinism for QA artefacts. |
| `LLM_MAX_RETRIES` | `4` | Exponential backoff via tenacity. |
| `LLM_REQUEST_TIMEOUT_S` | `120` | Per-request, not end-to-end. |
| `CHUNK_TARGET_TOKENS` | `900` | Raise for smarter models with bigger contexts. |
| `CHUNK_OVERLAP_TOKENS` | `120` | Keep 10-15 % of target for retrieval quality. |
| `MAX_DOC_PAGES_WARN` | `12000` | Logs a warning above this; no hard cap. |

### 4.3 Memory backends (see §6)

| Var | Accepted values |
|---|---|
| `SEMANTIC_MEMORY_BACKEND` | `inmemory` (default) · `qdrant` · `chroma` · `pgvector` |
| `EPISODIC_MEMORY_BACKEND` | `inmemory` (default) · `sqlite` · `redis` |
| `CROSSDOC_GRAPH_BACKEND`  | `networkx` (default) · `neo4j` |

**Important:** only `inmemory` / `networkx` are implemented today.
The config knobs exist as the seam where persistent adapters will plug
in without changing any caller.

---

## 5 · Notes by audience

### 5.1 For the Frontend / API team

- **Async by default.** Every public method is `async`. Wrap calls in
  an event loop or run from an async-native web framework (FastAPI,
  Litestar, aiohttp).
- **Long-running autonomous runs.** An autonomous pipeline call can
  take minutes on a real spec. **Do not block the HTTP response.**
  Launch it as a background task (Celery / ARQ / Dramatiq / FastAPI
  `BackgroundTasks`) and stream progress to the client via SSE /
  WebSocket. The brain emits episodic events during the run — read
  `brain.memory.episodic.recent(session_id)` to produce a progress
  feed.
- **Session resumption.** Both pipelines accept an optional
  `session_id`. Pass a user-owned id so a refreshed browser keeps its
  chat history and its in-flight run.
- **Detail level toggle.** The `DetailLevel` enum (`summary` vs
  `detailed`) is the single switch behind section 6 of the spec — wire
  it to a toggle in the UI.
- **Streaming chat.** The `LLMGateway.stream()` surface exists on the
  gateway, but `CopilotAgent` currently returns the full reply. If you
  need token-level streaming in the UI, expose `gateway.stream` behind
  a dedicated endpoint; do not re-route the copilot.
- **Citations.** `CopilotReply.citations` is the field to render as
  inline source chips ("spec_v3.pdf p.41").
- **Traceability UI.** The cross-document graph is queryable via
  `brain.memory.graph.coverage_matrix(requirement_ids)` and
  `brain.memory.graph.ancestors(node_id)`. That's the data backing a
  "why does this test exist?" drill-down.

### 5.2 For the API team specifically

Suggested minimum REST surface (shape, not prescription):

| Method | Path | Payload / Effect |
|---|---|---|
| `POST` | `/projects/{id}/ingest` | multipart file → returns `IngestionResult` |
| `POST` | `/projects/{id}/plans` | `{goal, detail_level}` → starts autonomous run, returns `session_id` |
| `GET`  | `/sessions/{id}` | returns current `AutonomousState` + progress events |
| `GET`  | `/projects/{id}/plans/{plan_id}` | returns `TestPlan` JSON |
| `POST` | `/chat` | `{project_id, session_id, message}` → `ChatReply` |
| `GET`  | `/trace/{artefact_id}` | returns upstream graph (ancestors) |

Every payload is already a Pydantic model — hand them to FastAPI /
Pydantic-v2-aware frameworks directly.

### 5.3 For DevOps / Infrastructure

- **Python 3.11+ required.** Uses `StrEnum`, PEP 604 unions, modern
  typing.
- **Install:** `pip install -e ".[dev]"` for development;
  `pip install .` for runtime.
- **Outbound calls.** The gateway talks to LLM providers; egress to
  `api.anthropic.com`, `api.openai.com`, `generativelanguage.googleapis.com`,
  or your chosen provider's endpoint is required. For air-gapped
  deployments, point `LLM_MODEL_*` at `ollama/...` on a local endpoint.
- **No filesystem writes** except what loaders read. Safe for
  read-only filesystems beyond the working dir.
- **No persistence.** The reference memory backends are in-process.
  A container restart drops everything. Plug in persistent backends
  (see §6) before production.
- **Logging.** `structlog` emits JSON-friendly structured events.
  Configure the renderer once at process start for your log stack
  (stdout JSON for Loki / CloudWatch / Datadog).
- **Observability.** Every agent run appends `agent_start` / `agent_done`
  / `agent_error` events to episodic memory. For OpenTelemetry, wrap
  `BaseAgent.invoke` with your tracer; a single shim gives you spans
  over every agent.
- **Secrets.** Only LLM API keys are secret-grade. Nothing else the
  brain reads needs secret storage.
- **GPU.** Not required. All heavy compute is on the provider side.
  (Unless you host a local model via Ollama / vLLM — then plan GPU
  accordingly.)

### 5.4 For Extension authors

Three seams are explicitly designed for extension. Each is one
Protocol / ABC — implement it and inject via `Brain.build(...)` args
(trivial refactor to accept the injected instance).

**A. New document format** — implement `ingestion.loaders.DocumentLoader`:
- yield `RawBlock`s lazily (streaming is non-negotiable),
- tag headings with a level,
- mark tables / code / formulas with their `kind` so the chunker keeps
  them atomic,
- register your loader in the `_LOADERS` + `_EXT_MAP` dicts at the
  bottom of `loaders.py`.

**B. Persistent semantic store** — implement `memory.base.SemanticStore`:
- `upsert(ids, vectors, payloads, namespace)`
- `query(vector, namespace, top_k, filters) → list[SearchHit]`
- `delete_namespace(namespace)`
- Construct it and pass as `semantic=` when building `MemoryManager`.
  Qdrant is the natural first target — its filter API maps 1:1 with
  `filters={"project_id": "...", "scope": "project"}`.

**C. Persistent graph store** — swap `CrossDocumentGraph` for a Neo4j
adapter. The surface is small (`add_node`, `add_link`, `neighbours`,
`coverage_matrix`, `ancestors`) — Cypher translations are mechanical.

**D. New agent** — subclass `agents.base.BaseAgent[TIn, TOut]`:
- implement `async run(inp: TIn) -> TOut`,
- add its system prompt to `prompts/library.py`,
- add a node to the relevant LangGraph in `graphs/`,
- update `OrchestratorAgent` if the autonomous graph should route to
  it.

---

## 6 · What's *not* in the box (yet)

These are deliberate out-of-scopes for this iteration. Owners of the
surrounding layers should assume they have to build / procure these.

| Area | Status | Notes for the owner |
|---|---|---|
| HTTP API | Not built | See §5.2 for a suggested shape. |
| Frontend | Not built | Designed to consume Pydantic JSON directly. |
| Auth / RBAC | Not built | Natural place: wrap `MemoryManager` methods with a `principal` arg. Scopes: read/write per project_id, admin for general KB. |
| Containers | Not built | Dockerfile is a 10-line `python:3.11-slim` + `pip install .`. |
| Persistent vector store | Interface only | Qdrant adapter is the recommended first impl. |
| Persistent episodic store | Interface only | SQLite is enough for single-instance deployments. |
| Persistent graph store | Interface only | Neo4j for multi-project / audit-at-scale. |
| LangGraph checkpointing | Ready to wire | Pass a `checkpointer=` to `.compile()` in `graphs/autonomous.py` to get time-travel and resumability. |
| Test suite | Placeholder only | `pytest` + `pytest-asyncio` already in `[dev]` extras. Fixtures should mock the `LLMGateway` Protocol. |
| Requirement dedup across documents | Within-doc only | Cross-doc dedup belongs in a post-ingest reducer. |
| Cost / token accounting | Per-response only | `LLMResponse.input_tokens / output_tokens` are populated. Aggregate them yourself. |

---

## 7 · Dev setup (for anyone touching the brain itself)

```bash
git clone <this repo>
cd ai-testplan-generator
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# fill in at least ONE provider API key + its matching LLM_MODEL_* vars

# Demo
python examples/run_autonomous.py path/to/spec.pdf
python examples/run_interactive.py path/to/spec.pdf
```

Type-check: `mypy src/`
Lint:       `ruff check src/`

---

## 8 · Invariants you can rely on

A short list of things that will *not* break between iterations:

1. `Brain.build()` returns a `Brain` with `.llm`, `.memory`,
   `.ingestion`, `.general_kb`, `.project_kb(id)`, `.context(...)`.
2. `AutonomousPipeline(brain).run(...)` returns an `AutonomousResult`
   with `.plan`, `.schedule`, `.state`, `.session_id`.
3. `InteractivePipeline(brain).session(project_id=...).ask(msg)`
   returns a `ChatReply` with `.assistant_message` and
   `.pending_action`.
4. Every id in the system is a stable string prefix:
   `doc_`, `sec_`, `ch_`, `req_`, `tc_`, `st_`, `ac_`, `plan_`, `ms_`,
   `res_`, `tr_`, `sess_`, `chat_`.
5. `sha256` on `Document` is computed from the raw bytes — safe for
   dedup and cache keys in your upload layer.
6. The `scope` field on `Document` is the only knob distinguishing
   general-KB content from project content. Set it correctly at ingest
   time; downstream retrieval partitioning relies on it.

---

## 9 · Who to ping

- **Brain internals, memory, agents, LangGraph:** the AI team (this
  repo).
- **New loaders, new agent roles, prompt tuning:** file an issue here
  with the document / use-case, we'll add it.
- **Performance on a specific model:** change the `LLM_MODEL_*` vars
  first — most "slow" reports are actually model-tier mismatches.

Happy wiring.
