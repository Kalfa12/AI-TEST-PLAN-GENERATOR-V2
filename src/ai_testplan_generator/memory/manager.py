"""MemoryManager - the single entry-point agents talk to.

Composes the four tiers (working / episodic / semantic / cross-doc) and
handles the embedding round-trips so agents don't need to.

Rules of the road:
  * All structural artefacts (Document / Section / Chunk / Requirement /
    TestCase) get registered on the cross-document graph AND (where
    text-searchable) the semantic store.
  * Embeddings always go through the LLM gateway - this is the only
    place in the codebase that calls `gateway.embed`, which keeps the
    provider boundary clean.
  * Retrieval is hybrid: we pull from semantic memory for "what's
    similar?" and walk the graph for "what's connected?". The returned
    `RetrievalBundle` carries both so agents can reason about either.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from ai_testplan_generator.config import Settings, get_settings
from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.llm import LLMGateway
from ai_testplan_generator.memory.base import (
    CrossDocumentGraphProtocol,
    EpisodeEvent,
    EpisodicStore,
    SearchHit,
    SemanticStore,
)
from ai_testplan_generator.memory.cross_document import InMemoryCrossDocumentGraph
from ai_testplan_generator.memory.episodic import InMemoryEpisodicStore
from ai_testplan_generator.memory.semantic import InMemorySemanticStore
from ai_testplan_generator.memory.working import WorkingMemory
from ai_testplan_generator.models import (
    Chunk,
    Document,
    Requirement,
    Resource,
    Section,
    TestCase,
    TestPlan,
)
from ai_testplan_generator.models.traceability import TraceKind, TraceLink

_log = structlog.get_logger(__name__)


class RetrievalBundle(BaseModel):
    """Everything an agent gets back from a cross-tier retrieval."""

    semantic_hits: list[SearchHit] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    graph_neighbours: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class _Artefacts:
    """Agent-side cache of structural objects (not a source of truth)."""

    documents: dict[str, Document] = field(default_factory=dict)
    sections: dict[str, Section] = field(default_factory=dict)
    chunks: dict[str, Chunk] = field(default_factory=dict)
    requirements: dict[str, Requirement] = field(default_factory=dict)
    resources: dict[str, Resource] = field(default_factory=dict)
    test_cases: dict[str, TestCase] = field(default_factory=dict)
    test_plans: dict[str, TestPlan] = field(default_factory=dict)
    test_case_plan_links: set[tuple[str, str]] = field(default_factory=set)


class MemoryManager:
    def __init__(
        self,
        *,
        llm: LLMGateway,
        settings: Settings | None = None,
        working: WorkingMemory | None = None,
        episodic: EpisodicStore | None = None,
        semantic: SemanticStore | None = None,
        graph: CrossDocumentGraphProtocol | None = None,
        artifact_repo: ArtifactRepository | None = None,
    ) -> None:
        self._llm = llm
        self._settings = settings or get_settings()
        self.working: WorkingMemory = working or WorkingMemory()
        self.episodic: EpisodicStore = episodic or self._resolve_episodic()
        self.semantic: SemanticStore = semantic or self._resolve_semantic()
        self.graph: CrossDocumentGraphProtocol = graph or self._resolve_graph()
        self.artifact_repo = artifact_repo
        self._store = _Artefacts()

    def _resolve_semantic(self) -> SemanticStore:
        """Pick the semantic store implementation based on config."""
        backend = self._settings.semantic_memory_backend
        if backend == "qdrant":
            from ai_testplan_generator.memory.backends.qdrant_store import QdrantSemanticStore

            _log.info("semantic_backend", backend="qdrant", url=self._settings.qdrant_url)
            return QdrantSemanticStore(
                url=self._settings.qdrant_url,
                api_key=self._settings.qdrant_api_key,
                embedding_dim=self._settings.qdrant_embedding_dim,
                collection_prefix=self._settings.qdrant_collection_prefix,
            )
        return InMemorySemanticStore()

    def _resolve_episodic(self) -> EpisodicStore:
        """Pick the episodic store implementation based on config.

        Note: SqliteEpisodicStore requires async init via SqliteEpisodicStore.create().
        For the sync code-path here we fall back to the in-memory store and expect
        callers that need SQLite to use build_episodic_store() from memory.backends.
        """
        backend = self._settings.episodic_memory_backend
        if backend == "sqlite":
            from ai_testplan_generator.memory.sqlite_store import SQLiteEpisodicStore

            _log.info("episodic_backend", backend="sqlite", path=self._settings.sqlite_episodic_path)
            return SQLiteEpisodicStore(db_path=self._settings.sqlite_episodic_path)
        return InMemoryEpisodicStore()

    def _resolve_graph(self) -> CrossDocumentGraphProtocol:
        """Pick the graph store implementation based on config."""
        backend = self._settings.crossdoc_graph_backend
        if backend == "neo4j":
            from ai_testplan_generator.memory.backends.neo4j_graph import Neo4jCrossDocumentGraph

            _log.info("graph_backend", backend="neo4j", uri=self._settings.neo4j_uri)
            return Neo4jCrossDocumentGraph(
                uri=self._settings.neo4j_uri,
                user=self._settings.neo4j_user,
                password=self._settings.neo4j_password,
            )
        return InMemoryCrossDocumentGraph()

    # ---- registration (write-path) -------------------------------------------

    async def hydrate(self) -> None:
        """Load persisted artefacts into the agent-side cache and graph index."""
        if self.artifact_repo is None:
            return
        snapshot = await self.artifact_repo.load_snapshot()
        for doc in snapshot.documents:
            self._remember_document(doc)
        for sec in snapshot.sections:
            self._remember_section(sec)
        for ch in snapshot.chunks:
            self._remember_chunk(ch)
        for req in snapshot.requirements:
            self._remember_requirement(req)
        for resource in snapshot.resources:
            self._remember_resource(resource)
        for plan in snapshot.test_plans:
            self._remember_test_plan(plan)
            for tc in plan.test_cases:
                self._remember_test_case(tc, plan_id=plan.id)
        for tc, plan_id in snapshot.test_cases:
            self._remember_test_case(tc, plan_id=plan_id)
        _log.info(
            "artifact_hydrate_done",
            n_documents=len(snapshot.documents),
            n_chunks=len(snapshot.chunks),
            n_requirements=len(snapshot.requirements),
            n_test_plans=len(snapshot.test_plans),
        )

    async def register_document(self, doc: Document) -> None:
        self._remember_document(doc)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_document(doc)

    async def register_sections(self, sections: Iterable[Section]) -> None:
        sections = list(sections)
        for sec in sections:
            self._remember_section(sec)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_sections(sections)

    async def register_chunks(self, chunks: Sequence[Chunk], *, embed: bool = True) -> None:
        if not chunks:
            return
        for ch in chunks:
            self._remember_chunk(ch)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_chunks(list(chunks))

        if not embed:
            return

        # Batch embeddings: the gateway handles provider-specific batching.
        texts = [ch.text for ch in chunks]
        vectors = await self._llm.embed(texts, input_type="passage")
        doc = self._store.documents.get(chunks[0].document_id)
        scope = doc.scope if doc else "project"
        project_id = doc.project_id if doc else None
        namespace = self._chunks_namespace(scope, project_id)
        payloads = [
            {
                "chunk_id": ch.id,
                "document_id": ch.document_id,
                "section_id": ch.section_id,
                "kind": ch.kind.value,
                "text": ch.text,
                "page_start": ch.page_start,
                "page_end": ch.page_end,
                "project_id": project_id,
                "scope": scope,
            }
            for ch in chunks
        ]
        await self.semantic.upsert(
            ids=[ch.id for ch in chunks],
            vectors=vectors,
            payloads=payloads,
            namespace=namespace,
        )

    async def register_requirements(self, requirements: Sequence[Requirement]) -> None:
        if not requirements:
            return
        for req in requirements:
            self._remember_requirement(req)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_requirements(list(requirements))

        # Embed requirements so the test-architect / copilot can retrieve
        # by intent.
        project_id = requirements[0].project_id
        namespace = f"requirements:{project_id or 'global'}"
        vectors = await self._llm.embed(
            [r.statement for r in requirements],
            input_type="passage",
        )
        payloads = [
            {
                "requirement_id": r.id,
                "project_id": r.project_id,
                "kind": r.kind.value,
                "title": r.title,
                "statement": r.statement,
                "priority": r.priority,
            }
            for r in requirements
        ]
        await self.semantic.upsert(
            ids=[r.id for r in requirements],
            vectors=vectors,
            payloads=payloads,
            namespace=namespace,
        )

    async def register_resource(self, resource: Resource) -> None:
        self._remember_resource(resource)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_resource(resource)

    async def list_resources_for_project(self, project_id: str) -> list[Resource]:
        if self.artifact_repo is not None:
            resources = await self.artifact_repo.list_resources(project_id)
            for resource in resources:
                self._remember_resource(resource)
            return resources
        return [
            resource
            for resource in self._store.resources.values()
            if resource.project_id == project_id
        ]

    async def get_resource(self, project_id: str, resource_id: str) -> Resource | None:
        if self.artifact_repo is not None:
            resource = await self.artifact_repo.get_resource(project_id, resource_id)
            if resource is not None:
                self._remember_resource(resource)
            return resource
        resource = self._store.resources.get(resource_id)
        if resource is None or resource.project_id != project_id:
            return None
        return resource

    async def delete_resource(self, project_id: str, resource_id: str) -> bool:
        ok = True
        if self.artifact_repo is not None:
            ok = await self.artifact_repo.delete_resource(project_id, resource_id)
        elif resource_id not in self._store.resources:
            ok = False
        self._store.resources.pop(resource_id, None)
        return ok

    async def register_test_cases(
        self, test_cases: Sequence[TestCase], *, plan_id: str | None = None
    ) -> None:
        for tc in test_cases:
            self._remember_test_case(tc, plan_id=plan_id)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_test_cases(list(test_cases), plan_id=plan_id)

    async def register_test_plan(self, plan: TestPlan) -> None:
        self._remember_test_plan(plan)
        await self.register_test_cases(plan.test_cases, plan_id=plan.id)
        if self.artifact_repo is not None:
            await self.artifact_repo.save_test_plan(plan)

    # ---- retrieval (read-path) -----------------------------------------------

    async def retrieve(
        self,
        query: str,
        *,
        project_id: str | None = None,
        scopes: Sequence[Literal["project", "general"]] = ("project", "general"),
        top_k_chunks: int = 10,
        top_k_requirements: int = 8,
        include_graph: bool = True,
    ) -> RetrievalBundle:
        """Hybrid retrieval: semantic hits + graph neighbours."""
        [qvec] = await self._llm.embed([query], input_type="query")
        semantic_hits: list[SearchHit] = []

        # Chunks: search each requested scope, then merge.
        for scope in scopes:
            ns = self._chunks_namespace(scope, project_id)
            hits = await self.semantic.query(qvec, namespace=ns, top_k=top_k_chunks)
            semantic_hits.extend(hits)

        # Requirements.
        req_ns = f"requirements:{project_id or 'global'}"
        req_hits = await self.semantic.query(qvec, namespace=req_ns, top_k=top_k_requirements)

        chunks = [self._store.chunks[h.id] for h in semantic_hits if h.id in self._store.chunks]
        requirements = [
            self._store.requirements[h.id]
            for h in req_hits
            if h.id in self._store.requirements
        ]

        graph_neighbours: list[dict[str, Any]] = []
        if include_graph:
            for ch in chunks:
                for nbr, data in self.graph.neighbours(ch.id):
                    graph_neighbours.append({"from": ch.id, "to": nbr, **data})

        return RetrievalBundle(
            semantic_hits=semantic_hits + req_hits,
            chunks=chunks,
            requirements=requirements,
            graph_neighbours=graph_neighbours,
        )

    async def get_chunks_by_ids(self, ids: Iterable[str]) -> list[Chunk]:
        ids = list(ids)
        missing = [i for i in ids if i not in self._store.chunks]
        if missing and self.artifact_repo is not None:
            for ch in await self.artifact_repo.get_chunks_by_ids(missing):
                self._remember_chunk(ch)
        return [self._store.chunks[i] for i in ids if i in self._store.chunks]

    async def get_documents_for_project(self, project_id: str | None) -> list[Document]:
        if self.artifact_repo is not None:
            docs = await self.artifact_repo.list_documents(project_id)
            for doc in docs:
                self._remember_document(doc)
            return docs
        return [d for d in self._store.documents.values() if d.project_id == project_id]

    async def get_chunks_for_document(self, document_id: str) -> list[Chunk]:
        if self.artifact_repo is not None:
            chunks = await self.artifact_repo.list_chunks_for_document(document_id)
            for ch in chunks:
                self._remember_chunk(ch)
            return chunks
        return [ch for ch in self._store.chunks.values() if ch.document_id == document_id]

    async def get_chunks_for_project(self, project_id: str | None) -> list[Chunk]:
        if self.artifact_repo is not None:
            chunks = await self.artifact_repo.list_chunks_for_project(project_id)
            for ch in chunks:
                self._remember_chunk(ch)
            return chunks
        doc_ids = {
            d.id for d in self._store.documents.values() if d.project_id == project_id
        }
        return [ch for ch in self._store.chunks.values() if ch.document_id in doc_ids]

    async def get_requirements_for_project(self, project_id: str | None) -> list[Requirement]:
        if self.artifact_repo is not None:
            requirements = await self.artifact_repo.list_requirements(project_id)
            for req in requirements:
                self._remember_requirement(req)
            return requirements
        return [r for r in self._store.requirements.values() if r.project_id == project_id]

    async def get_test_plans_for_project(self, project_id: str | None) -> list[TestPlan]:
        if self.artifact_repo is not None:
            plans = await self.artifact_repo.list_test_plans(project_id)
            for plan in plans:
                self._remember_test_plan(plan)
                for tc in plan.test_cases:
                    self._remember_test_case(tc, plan_id=plan.id)
            return plans
        return [p for p in self._store.test_plans.values() if p.project_id == project_id]

    async def get_test_plan(self, plan_id: str) -> TestPlan | None:
        if self.artifact_repo is not None:
            plan = await self.artifact_repo.get_test_plan(plan_id)
            if plan is not None:
                self._remember_test_plan(plan)
                for tc in plan.test_cases:
                    self._remember_test_case(tc, plan_id=plan.id)
            return plan
        return self._store.test_plans.get(plan_id)

    async def delete_document(self, doc_id: str) -> None:
        self._store.documents.pop(doc_id, None)
        for ch_id, ch in list(self._store.chunks.items()):
            if ch.document_id == doc_id:
                self._store.chunks.pop(ch_id, None)
        for sec_id, sec in list(self._store.sections.items()):
            if sec.document_id == doc_id:
                self._store.sections.pop(sec_id, None)
        for req_id, req in list(self._store.requirements.items()):
            if req.source_document_id == doc_id:
                self._store.requirements.pop(req_id, None)
        if self.artifact_repo is not None:
            await self.artifact_repo.delete_document(doc_id)

    async def delete_test_plan(self, plan_id: str) -> None:
        self._store.test_plans.pop(plan_id, None)
        if self.artifact_repo is not None:
            await self.artifact_repo.delete_test_plan(plan_id)

    async def delete_project_artefacts(self, project_id: str) -> int:
        docs = await self.get_documents_for_project(project_id)
        for doc in docs:
            await self.delete_document(doc.id)
        for plan in await self.get_test_plans_for_project(project_id):
            await self.delete_test_plan(plan.id)
        return len(docs)

    # ---- episodic convenience -----------------------------------------------

    async def log_event(
        self, session_id: str, actor: str, kind: str, content: str, **metadata: Any
    ) -> None:
        await self.episodic.append(
            EpisodeEvent(
                ts=datetime.now(timezone.utc),
                session_id=session_id,
                actor=actor,
                kind=kind,
                content=content,
                metadata=dict(metadata),
            )
        )

    # ---- internals ----------------------------------------------------------

    def _remember_document(self, doc: Document) -> None:
        if doc.id in self._store.documents:
            self._store.documents[doc.id] = doc
            return
        self._store.documents[doc.id] = doc
        self.graph.add_node(
            doc.id,
            "Document",
            title=doc.title,
            kind=doc.kind.value,
            scope=doc.scope,
            project_id=doc.project_id,
        )

    def _remember_section(self, sec: Section) -> None:
        if sec.id in self._store.sections:
            self._store.sections[sec.id] = sec
            return
        self._store.sections[sec.id] = sec
        self.graph.add_node(sec.id, "Section", title=sec.title, level=sec.level)
        self.graph.add_link(
            TraceLink(
                kind=TraceKind.DERIVES_FROM,
                source_id=sec.id,
                source_type="Section",
                target_id=sec.document_id,
                target_type="Document",
                confidence=1.0,
            )
        )

    def _remember_chunk(self, ch: Chunk) -> None:
        if ch.id in self._store.chunks:
            self._store.chunks[ch.id] = ch
            return
        self._store.chunks[ch.id] = ch
        self.graph.add_node(ch.id, "Chunk", kind=ch.kind.value, tokens=ch.token_count)
        if ch.section_id:
            self.graph.add_link(
                TraceLink(
                    kind=TraceKind.DERIVES_FROM,
                    source_id=ch.id,
                    source_type="Chunk",
                    target_id=ch.section_id,
                    target_type="Section",
                    confidence=1.0,
                )
            )

    def _remember_requirement(self, req: Requirement) -> None:
        if req.id in self._store.requirements:
            self._store.requirements[req.id] = req
            return
        self._store.requirements[req.id] = req
        self.graph.add_node(
            req.id,
            "Requirement",
            kind=req.kind.value,
            priority=req.priority,
            project_id=req.project_id,
        )
        for ch_id in req.source_chunk_ids:
            self.graph.add_link(
                TraceLink(
                    kind=TraceKind.DERIVES_FROM,
                    source_id=req.id,
                    source_type="Requirement",
                    target_id=ch_id,
                    target_type="Chunk",
                    confidence=1.0,
                )
            )

    def _remember_resource(self, resource: Resource) -> None:
        self._store.resources[resource.id] = resource

    def _remember_test_case(self, tc: TestCase, *, plan_id: str | None = None) -> None:
        is_new = tc.id not in self._store.test_cases
        self._store.test_cases[tc.id] = tc
        if is_new:
            self.graph.add_node(tc.id, "TestCase", title=tc.title, risk=tc.risk_level)
            for req_id in tc.requirement_ids:
                self.graph.add_link(
                    TraceLink(
                        kind=TraceKind.COVERS,
                        source_id=tc.id,
                        source_type="TestCase",
                        target_id=req_id,
                        target_type="Requirement",
                        confidence=1.0,
                    )
                )
        if plan_id and (tc.id, plan_id) not in self._store.test_case_plan_links:
            self._store.test_case_plan_links.add((tc.id, plan_id))
            self.graph.add_link(
                TraceLink(
                    kind=TraceKind.DERIVES_FROM,
                    source_id=tc.id,
                    source_type="TestCase",
                    target_id=plan_id,
                    target_type="TestPlan",
                    confidence=1.0,
                )
            )

    def _remember_test_plan(self, plan: TestPlan) -> None:
        if plan.id in self._store.test_plans:
            self._store.test_plans[plan.id] = plan
            return
        self._store.test_plans[plan.id] = plan
        self.graph.add_node(plan.id, "TestPlan", title=plan.title, project_id=plan.project_id)

    @staticmethod
    def _chunks_namespace(
        scope: Literal["project", "general"], project_id: str | None
    ) -> str:
        if scope == "general":
            return "chunks:general"
        return f"chunks:{project_id or 'global'}"
