# API

The backend exposes a REST API through FastAPI.

## Local API

When running locally:

```text
http://localhost:8000
```

## OpenAPI

FastAPI exposes the OpenAPI schema at:

```text
http://localhost:8000/openapi.json
```

Interactive docs are available at:

```text
http://localhost:8000/docs
```

## Main API Areas

| Area | Purpose |
| --- | --- |
| `/auth` | Login, refresh tokens, API keys |
| `/projects` | Project CRUD and project dashboard data |
| `/documents` | Upload and inspect documents |
| `/plans` | Generate and retrieve test plans |
| `/planning` | Resources, assignments, and follow-up |
| `/traceability` | Coverage and graph data |
| `/quality` | Defect and quality checks |
| `/chat` | Contextual chat |
| `/events` | Progress and realtime events |
| `/healthz`, `/readyz` | Health checks |

## Regenerating Frontend Client

```bash
cd frontend
npm run gen:api
```

This command dumps the OpenAPI schema and regenerates the TypeScript client.
