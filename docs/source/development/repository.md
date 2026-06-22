# Repository Guide

## Structure

```text
.
├── src/ai_testplan_generator/   Backend application
├── frontend/                    React frontend
├── tests/                       Backend tests
├── docs/                        Documentation and demo documents
├── ops/                         Docker, Helm, monitoring assets
├── scripts/                     Utility scripts
├── examples/                    Example pipeline scripts
└── evals/                       Evaluation assets
```

## Backend Code Style

Backend code is Python 3.11+ with Pydantic models and async FastAPI routes.

## Frontend Code Style

Frontend code is TypeScript with React components organized by feature.

## Important Scripts

| Command | Purpose |
| --- | --- |
| `python scripts/create_admin.py` | Create a local admin user |
| `python scripts/dump_openapi.py openapi.json` | Export backend OpenAPI schema |
| `python scripts/seed_demo_data.py` | Seed demo data |
| `npm run gen:api` | Regenerate frontend API client |

## Documentation Location

Read the Docs source lives in:

```text
docs/source/
```
