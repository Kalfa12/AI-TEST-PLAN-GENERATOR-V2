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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def models(self) -> ModelTier:
        return ModelTier()  # re-reads env; keeps tiers independently overridable


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
