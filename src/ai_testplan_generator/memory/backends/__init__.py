"""Factory helpers for all persistent memory backends.

Each `build_*` function reads the relevant settings and returns the
appropriate concrete implementation.
"""

from __future__ import annotations

from ai_testplan_generator.config import Settings
from ai_testplan_generator.memory.base import (
    CrossDocumentGraphProtocol,
    EpisodicStore,
    SemanticStore,
)

__all__ = [
    "build_semantic_store",
    "build_episodic_store",
    "build_graph_store",
]


def build_semantic_store(settings: Settings) -> SemanticStore:
    backend = settings.semantic_memory_backend
    if backend == "qdrant":
        from ai_testplan_generator.memory.backends.qdrant_store import QdrantSemanticStore

        return QdrantSemanticStore(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            embedding_dim=settings.qdrant_embedding_dim,
            collection_prefix=settings.qdrant_collection_prefix,
        )
    from ai_testplan_generator.memory.semantic import InMemorySemanticStore

    return InMemorySemanticStore()


async def build_episodic_store(settings: Settings) -> EpisodicStore:
    backend = settings.episodic_memory_backend
    if backend == "sqlite":
        from ai_testplan_generator.memory.backends.sqlite_episodic import SqliteEpisodicStore

        return await SqliteEpisodicStore.create(db_path=settings.sqlite_episodic_path)
    from ai_testplan_generator.memory.episodic import InMemoryEpisodicStore

    return InMemoryEpisodicStore()


def build_graph_store(settings: Settings) -> CrossDocumentGraphProtocol:
    backend = settings.crossdoc_graph_backend
    if backend == "neo4j":
        from ai_testplan_generator.memory.backends.neo4j_graph import Neo4jCrossDocumentGraph

        return Neo4jCrossDocumentGraph(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
    from ai_testplan_generator.memory.cross_document import InMemoryCrossDocumentGraph

    return InMemoryCrossDocumentGraph()
