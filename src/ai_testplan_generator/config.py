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

    # HTTP API settings (M05)
    api_debug: bool = Field(default=False, alias="API_DEBUG")
    # Comma-separated origins; use ["*"] for development.
    api_cors_origins: list[str] = Field(default=["*"], alias="API_CORS_ORIGINS")
    # SQLite database for project/user domain repos (M10).
    app_db_path: str = Field(default="data/app.db", alias="APP_DB_PATH")
    # Max multipart upload size in bytes (M06).
    max_upload_size_bytes: int = Field(default=100 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")
    # Files larger than this threshold are backgrounded instead of inlined (M06).
    large_doc_threshold_bytes: int = Field(default=5 * 1024 * 1024, alias="LARGE_DOC_THRESHOLD_BYTES")

    # JWT authentication settings (M13)
    # Algorithm used to sign JWTs. RS256 requires JWT_PRIVATE_KEY_PATH + JWT_PUBLIC_KEY_PATH.
    jwt_algorithm: str = Field(default="RS256", alias="JWT_ALGORITHM")
    # Path to PEM-encoded RSA private key (RS256 mode). Leave blank to use HS256.
    jwt_private_key_path: str | None = Field(default=None, alias="JWT_PRIVATE_KEY_PATH")
    # Path to PEM-encoded RSA public key (RS256 mode). Leave blank to use HS256.
    jwt_public_key_path: str | None = Field(default=None, alias="JWT_PUBLIC_KEY_PATH")
    # Shared secret for HS256 fallback (local dev only). Must be set when no key paths given.
    jwt_secret: str = Field(default="changeme-local-dev-only", alias="JWT_SECRET")
    # Access token lifetime in seconds (default 15 min).
    jwt_access_token_ttl_seconds: int = Field(default=900, alias="JWT_ACCESS_TOKEN_TTL_SECONDS")
    # Refresh token lifetime in seconds (default 14 days).
    jwt_refresh_token_ttl_seconds: int = Field(default=1209600, alias="JWT_REFRESH_TOKEN_TTL_SECONDS")

    # Blob encryption at rest (M16)
    # Base64url-encoded 32-byte Fernet key. When set, all blobs are envelope-encrypted.
    blob_encryption_key: str | None = Field(default=None, alias="BLOB_ENCRYPTION_KEY")
    # Key-encryption-key version prefix written into each blob key.
    blob_kek_version: str = Field(default="v1", alias="BLOB_KEK_VERSION")

    # Redis connection (M17/M18) — shared by ARQ job queue and event broker.
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    # Maximum concurrent ARQ worker jobs per worker process (M17).
    job_worker_concurrency: int = Field(default=4, alias="JOB_WORKER_CONCURRENCY")

    # Event broker backend (M18). Use "redis" in production with a running Redis instance.
    event_broker_backend: Literal["inmemory", "redis"] = Field(
        default="inmemory", alias="EVENT_BROKER_BACKEND"
    )

    # OpenTelemetry tracing (M20)
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_service_name: str = Field(default="aitpg-api", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    # Prometheus metrics (M21)
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")

    # Structured logging (M22)
    log_format: Literal["json", "console"] = Field(default="console", alias="LOG_FORMAT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # LLM cost tracking (M23)
    cost_tracking_enabled: bool = Field(default=True, alias="COST_TRACKING_ENABLED")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def models(self) -> ModelTier:
        return ModelTier()  # re-reads env; keeps tiers independently overridable


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
