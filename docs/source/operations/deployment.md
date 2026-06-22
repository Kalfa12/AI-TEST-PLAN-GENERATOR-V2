# Deployment

The repository includes deployment assets for containerized environments.

## Docker Images

The backend image is built from:

```text
Dockerfile
```

The frontend image is built from:

```text
frontend/Dockerfile
```

## Helm Chart

The Helm chart is located in:

```text
ops/helm/aitpg/
```

It includes templates for:

- API deployment;
- worker deployment;
- service;
- ingress;
- config map;
- secret;
- HPA;
- PDB.

## Production Checklist

Before production deployment:

- configure real secrets;
- configure explicit CORS origins;
- enable HTTPS;
- use a production database strategy;
- select persistent semantic and graph stores;
- configure backup and retention;
- configure monitoring;
- verify LLM provider rate limits and budgets;
- test document upload with realistic files.
