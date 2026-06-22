# Docker

Docker Compose is the easiest way to run the complete stack.

## Start

```bash
cp .env.example .env
docker compose up --build
```

Frontend:

```text
http://localhost:8080
```

Backend:

```text
http://localhost:8000
```

## Services

The compose stack starts:

- frontend;
- API;
- worker;
- Redis;
- Qdrant;
- Neo4j.

Optional observability:

```bash
docker compose --profile observability up --build
```

This also starts:

- Prometheus;
- Grafana;
- Jaeger.

## Reset Local Data

Stop services:

```bash
docker compose down
```

Remove volumes only when you intentionally want to erase service data:

```bash
docker compose down -v
```

Be careful: this removes Redis, Qdrant, Neo4j, Prometheus, and Grafana volumes.
