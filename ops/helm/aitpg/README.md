# aitpg Helm Chart

Deploys the AI Test Plan Generator API and ARQ worker to a Kubernetes cluster.

## Prerequisites

| Component | Requirement |
|---|---|
| Kubernetes | >= 1.26 |
| Helm | >= 3.12 |
| metrics-server | Required for the API HPA (CPU utilization). Install via `helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server`. |
| Ingress controller | Required when `ingress.enabled=true`. Default class is `nginx`. |
| Custom metrics adapter | Required when `hpa.worker.enabled=true`. A prometheus-adapter configured to expose `aitpg_job_queue_depth` via `custom.metrics.k8s.io` is the recommended approach. |
| Redis | Must be reachable at the URL set in `config.REDIS_URL`. Use the Bitnami Redis chart or a managed service. |
| Qdrant | Must be reachable at `config.QDRANT_URL` when `config.SEMANTIC_MEMORY_BACKEND=qdrant`. |
| Neo4j | Must be reachable at `config.NEO4J_URI` when `config.CROSSDOC_GRAPH_BACKEND=neo4j`. |

## Quick start

```bash
helm upgrade --install aitpg ops/helm/aitpg \
  --set secrets.ANTHROPIC_API_KEY=sk-... \
  --set secrets.JWT_SECRET=... \
  --set config.REDIS_URL=redis://my-redis:6379/0
```

## Configuration

All knobs are in [values.yaml](values.yaml) with inline comments.
Secret values should be supplied via `--set secrets.*` or an external-secrets
operator — do not commit real secrets to source control.

## Upgrading

`helm upgrade --install aitpg ops/helm/aitpg` is idempotent.

Rolling updates: the API deployment uses the default RollingUpdate strategy.
The PodDisruptionBudget ensures at least one replica is available during
node drains.

## Worker HPA

The worker HPA (`hpa.worker.enabled`) requires the `aitpg_job_queue_depth`
metric to be available in the Kubernetes custom metrics API. Steps:

1. Deploy prometheus-adapter and configure a rule mapping
   `aitpg_job_queue_depth` to `custom.metrics.k8s.io`.
2. Verify: `kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1"`.
3. Set `hpa.worker.enabled=true` and upgrade the release.
