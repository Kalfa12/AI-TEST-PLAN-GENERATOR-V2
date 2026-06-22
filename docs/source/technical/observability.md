# Observability

The project includes observability hooks for local and production-like deployments.

## Logging

Structured logging is configured through:

```text
src/ai_testplan_generator/telemetry/logging.py
```

Environment variables:

```bash
LOG_FORMAT=console
LOG_LEVEL=INFO
```

For production log shipping:

```bash
LOG_FORMAT=json
```

## Metrics

Prometheus metrics can be enabled with:

```bash
METRICS_ENABLED=true
```

The Docker Compose stack includes an optional Prometheus profile.

## Tracing

OpenTelemetry tracing can be enabled with:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=aitpg-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

The Docker Compose stack includes Jaeger under the observability profile.

## Cost Tracking

LLM usage and estimated cost tracking are controlled by:

```bash
COST_TRACKING_ENABLED=true
```

Cost accuracy depends on token accounting and provider pricing configuration.
