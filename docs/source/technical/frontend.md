# Frontend

The frontend is a React application located in `frontend/`.

## Technology

- React 18;
- TypeScript;
- Vite;
- TanStack Query;
- TanStack Router;
- Tailwind CSS;
- jsPDF for client-side PDF export.

## Main Feature Areas

| Directory | Responsibility |
| --- | --- |
| `features/auth` | Login, token storage, API keys |
| `features/projects` | Project list and project dashboard |
| `features/documents` | Upload drawer and document table |
| `features/requirements` | Requirement table |
| `features/plans` | Plan generation, progress, detail, export |
| `features/chat` | Contextual chat |
| `features/traceability` | Coverage and graph views |
| `features/quality` | Defect and quality panels |
| `features/admin` | Admin views |

## API Client

The frontend uses typed API helpers in:

```text
frontend/src/lib/api/
```

The generated OpenAPI client can be regenerated with:

```bash
cd frontend
npm run gen:api
```

## Local Development

```bash
cd frontend
npm install
npm run dev
```

The development frontend usually runs on:

```text
http://localhost:5173
```
