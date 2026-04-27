# Modifications Log

This file tracks recent changes made to the environment and configurations to facilitate local manual testing, especially for Phase 6 (Frontend) development. 

## 1. Docker Compose Configuration (`docker-compose.yml`)

Several modifications were made to ensure the backend starts up quickly and reliably without requiring complex external database configurations.

* **Added `build` context to the `worker` service:** The `worker` service was attempting to pull the `aitpg-api:local` image from Docker Hub (which failed because the repository doesn't exist). Added the `build` directive (pointing to `Dockerfile` and context `.`) so Docker Compose knows to build it locally, mirroring the `api` service.
* **Switched Semantic Memory to In-Memory:** In the `environment` blocks for both `api` and `worker`, changed `SEMANTIC_MEMORY_BACKEND: "qdrant"` to `"inmemory"`. This allows local testing without relying on the Qdrant vector database.
* **Pointed to correct `.env` file:** Changed the `env_file` setting from `ops/compose/env.example` to `.env` so it correctly loads the user's local API keys and LLM configuration instead of failing with missing OpenAI key errors.
* **Removed Failing Dependencies:** Removed `qdrant` and `neo4j` from the `depends_on` list of the `api` service. Previously, `qdrant` was failing its `healthcheck`, which completely blocked the `api` container from starting. 

### ⚠️ Affected Phases & How to Revert
* **Affected Phases:** **Phase 7 (Deployment)** and **Phase 8 (Integration Tests)**. These phases will likely require real persistence with Qdrant and Neo4j rather than in-memory storage.
* **How to Revert:** 
  1. In `docker-compose.yml`, change `SEMANTIC_MEMORY_BACKEND: "inmemory"` back to `"qdrant"` (and ensure `CROSSDOC_GRAPH_BACKEND` is set appropriately).
  2. Re-add `qdrant` and `neo4j` under the `depends_on` section of the `api` service.
  3. Ensure the `healthcheck` for the `qdrant` service in `docker-compose.yml` is correctly configured to pass (e.g., using a valid `wget` or `curl` command compatible with the Qdrant image) so the `api` service doesn't hang waiting for it.

## 2. Database Seeding

To allow immediate testing of the frontend login screen (M24/M25), a default user was manually seeded into the SQLite core database (`data/app.db`). (An initial erroneous insertion was also made to `data/episodic.db`, but the correct insertion is in `app.db`).

* **Email:** `admin@example.com`
* **Password:** `password123`
* *Note: The database does not currently have an automated seed script for this; it was injected manually using a python script calling `UserRepository`.*
* *Note 2: The user was also manually added as the `owner` to the existing project `proj_62d9e9b878` in `project_members` because the frontend currently hardcodes/caches this project ID on login.*

### ⚠️ Affected Phases & How to Revert
* **Affected Phases:** **Phase 8 (E2E Tests)**. If E2E Playwright/Cypress tests expect a pristine database or attempt to register this exact email, it may cause conflicts.
* **How to Revert:** 
  1. The simplest way to revert is to delete the `data/app.db` and `data/episodic.db` files. The API will recreate them cleanly on the next startup.
  2. Alternatively, future agents can write an explicit teardown script or a `DELETE FROM users WHERE email='admin@example.com';` query if they need to clear the state programmatically.

## 3. Bug Fixes for Local Execution

* **Fixed API Gateway API Key Resolution:** Renamed `GOOGLE_API_KEY` to `GEMINI_API_KEY` inside the `.env` file to ensure LiteLLM correctly routes requests to the Gemini provider without throwing an OpenAI `401 Unauthorized` exception.
* **Fixed Background Job Queue Initialization (`app.py`):** Fixed an `AttributeError` caused by a deprecated ARQ import. Changed `arq.RedisSettings` to `from arq.connections import RedisSettings` inside `src/ai_testplan_generator/api/app.py`. Previously, this import failure silently forced `job_queue` to `None`, which crashed the API when attempting to generate test plans (`AttributeError: 'NoneType' object has no attribute 'enqueue'`).
* **Fixed WebSocket Dependency Injection (`deps.py`):** Updated `get_brain` in `src/ai_testplan_generator/api/deps.py` to accept `(request: Request = None, websocket: WebSocket = None)` instead of strictly requiring a `Request`. This fixes a `TypeError` that crashed the `/chat/{session_id}/stream` WebSocket endpoint when the frontend attempted to connect to the Copilot.
* **Fixed In-Memory Cross-Container Sync Bug (`app.py`):** The `Pipeline completed without producing a plan` error was caused by the system using an `inmemory` semantic backend while dispatching jobs to a separate Redis `worker` container. Because the worker ran in a separate process, its in-memory database was completely empty, and it could not see the documents uploaded via the API container, forcing it to immediately exit. Modified `src/ai_testplan_generator/api/app.py` to automatically instantiate `FakeJobQueue` and run tasks synchronously within the API process if `cfg.semantic_memory_backend == "inmemory"`.
* **Fixed LiteLLM DeepSeek Compatibility (`litellm_gateway.py`):** Changed the `response_format` requirement from strict `json_schema` to standard `json_object` in `src/ai_testplan_generator/llm/litellm_gateway.py`. DeepSeek's API natively supports JSON mode but throws a 400 Bad Request error if the strict `json_schema` type is requested.
