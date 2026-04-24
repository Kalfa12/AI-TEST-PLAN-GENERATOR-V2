"""Central configuration.

Everything swappable lives here. Changing `LLM_MODEL_SMART` in `.env` is the
only thing required to re-route reasoning from Claude to GPT-5 to Gemini to a
local Ollama model - no code changes, no re-deploys beyond the env var.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelTier(BaseSettings):
    """Three-tier model policy that every agent can pick from by role.

    Agents don't know which provider they're talking to - they ask for a
    *tier* ("smart" / "balanced" / "fast") and the gateway resolves it.
    """

    smart: str = Field(default="claude-opus-4-1-20250805", alias="LLM_MODEL_SMART")
    balanced: str = Field(default="claude-sonnet-4-5-20250929", alias="LLM_MODEL_BALANCED")
    fast: str = Field(default="claude-haiku-4-5-20251001", alias="LLM_MODEL_FAST")
    embedding: str = Field(default="text-embedding-3-large", alias="LLM_MODEL_EMBEDDING")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)


class Settings(BaseSettings):
    """Root settings - the single knob-box for the whole brain."""

    # LLM behaviour
    default_temperature: float = Field(default=0.1, alias="LLM_DEFAULT_TEMPERATURE")
    max_retries: int = Field(default=4, alias="LLM_MAX_RETRIES")
    request_timeout_s: int = Field(default=120, alias="LLM_REQUEST_TIMEOUT_S")

    # Ingestion
    chunk_target_tokens: int = Field(default=900, alias="CHUNK_TARGET_TOKENS")
    chunk_overlap_tokens: int = Field(default=120, alias="CHUNK_OVERLAP_TOKENS")
    max_doc_pages_warn: int = Field(default=12000, alias="MAX_DOC_PAGES_WARN")

    # Memory backends
    semantic_memory_backend: Literal["inmemory", "qdrant", "chroma", "pgvector"] = Field(
        default="inmemory", alias="SEMANTIC_MEMORY_BACKEND"
    )
    episodic_memory_backend: Literal["inmemory", "sqlite", "redis"] = Field(
        default="inmemory", alias="EPISODIC_MEMORY_BACKEND"
    )
    crossdoc_graph_backend: Literal["networkx", "neo4j"] = Field(
        default="networkx", alias="CROSSDOC_GRAPH_BACKEND"
    )

    # Qdrant settings (used when SEMANTIC_MEMORY_BACKEND=qdrant)
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_embedding_dim: int = Field(default=3072, alias="QDRANT_EMBEDDING_DIM")
    qdrant_collection_prefix: str = Field(default="aitpg", alias="QDRANT_COLLECTION_PREFIX")

    # SQLite settings (used when EPISODIC_MEMORY_BACKEND=sqlite)
    sqlite_episodic_path: str = Field(default="data/episodic.db", alias="SQLITE_EPISODIC_PATH")

    # Neo4j settings (used when CROSSDOC_GRAPH_BACKEND=neo4j)
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="changeme", alias="NEO4J_PASSWORD")

    # Blob store settings (M04)
    blob_store_backend: Literal["local", "s3"] = Field(default="local", alias="BLOB_STORE_BACKEND")
    blob_store_local_root: str = Field(default="./data/blobs", alias="BLOB_STORE_LOCAL_ROOT")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def models(self) -> ModelTier:
        return ModelTier()  # re-reads env; keeps tiers independently overridable


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
