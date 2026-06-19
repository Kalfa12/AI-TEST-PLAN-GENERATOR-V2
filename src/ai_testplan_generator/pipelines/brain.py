"""`Brain` - the single composition root.

Wires together the LLM gateway, memory tiers, ingestion pipeline, and
knowledge bases. Both pipelines (autonomous + interactive) take a
`Brain` and use it to spawn per-session agent contexts.

This is the thing most consumers will instantiate. Everything else is
reachable through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_testplan_generator.agents.base import AgentContext
from ai_testplan_generator.config import Settings, get_settings
from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.ingestion.pipeline import IngestionPipeline
from ai_testplan_generator.knowledge import GeneralKnowledgeBase, ProjectKnowledgeBase
from ai_testplan_generator.llm import LLMGateway, get_gateway
from ai_testplan_generator.memory.manager import MemoryManager


@dataclass
class Brain:
    settings: Settings
    llm: LLMGateway
    memory: MemoryManager
    ingestion: IngestionPipeline
    general_kb: GeneralKnowledgeBase
    # Optional event broker — injected by the API layer so agents can
    # publish per-step SSE events to the frontend.
    event_broker: Any | None = None

    def project_kb(self, project_id: str) -> ProjectKnowledgeBase:
        return ProjectKnowledgeBase(self.ingestion, project_id=project_id)

    def context(self, *, session_id: str, project_id: str | None = None) -> AgentContext:
        return AgentContext(
            llm=self.llm,
            memory=self.memory,
            session_id=session_id,
            project_id=project_id,
            event_broker=self.event_broker,
        )

    @classmethod
    def build(
        cls,
        *,
        llm: LLMGateway | None = None,
        settings: Settings | None = None,
        artifact_repo: ArtifactRepository | None = None,
    ) -> "Brain":
        settings = settings or get_settings()
        llm = llm or get_gateway()
        memory = MemoryManager(llm=llm, settings=settings, artifact_repo=artifact_repo)
        ingestion = IngestionPipeline(llm=llm, memory=memory, settings=settings)
        general = GeneralKnowledgeBase(ingestion)
        return cls(
            settings=settings,
            llm=llm,
            memory=memory,
            ingestion=ingestion,
            general_kb=general,
        )
