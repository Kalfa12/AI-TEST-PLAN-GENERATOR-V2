# Configuration

Configuration is loaded from environment variables and `.env`.

The reference file is:

```text
.env.example
```

## LLM Models

```bash
LLM_MODEL_SMART=...
LLM_MODEL_BALANCED=...
LLM_MODEL_FAST=...
LLM_MODEL_EMBEDDING=...
```

## Provider Keys

Only configure the providers you use:

```bash
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
NVIDIA_API_KEY=
GOOGLE_API_KEY=
```

## NVIDIA Embeddings

```bash
LLM_MODEL_EMBEDDING=nvidia/nv-embed-v1
NVIDIA_API_KEY=...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_EMBEDDING_BATCH_SIZE=50
NVIDIA_EMBEDDING_TRUNCATE=NONE
```

## Memory Backends

```bash
SEMANTIC_MEMORY_BACKEND=inmemory
EPISODIC_MEMORY_BACKEND=sqlite
CROSSDOC_GRAPH_BACKEND=networkx
```

For production-like semantic memory:

```bash
SEMANTIC_MEMORY_BACKEND=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_EMBEDDING_DIM=4096
```

## App Database

```bash
APP_DB_PATH=data/app.db
```

## Authentication

```bash
JWT_ALGORITHM=HS256
JWT_SECRET=change-this-secret
```

For production, prefer RS256 with key files.

## Upload Limits

```bash
MAX_UPLOAD_SIZE_BYTES=104857600
LARGE_DOC_THRESHOLD_BYTES=5242880
```
