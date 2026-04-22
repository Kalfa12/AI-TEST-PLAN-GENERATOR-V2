"""Shared test fixtures for the AI Test Plan Generator test suite.

Provides a mocked LLMGateway, a pre-built Brain with in-memory backends,
and factory helpers for creating test data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio

from ai_testplan_generator.config import Settings
from ai_testplan_generator.llm.base import (
    ChatMessage,
    LLMGateway,
    LLMResponse,
    ModelRole,
)
from ai_testplan_generator.models import (
    Chunk,
    ChunkKind,
    DetailLevel,
    Document,
    DocumentKind,
    Requirement,
    RequirementKind,
    Section,
    TestCase,
    TestPlan,
    TestStep,
    AcceptanceCriterion,
)
from ai_testplan_generator.pipelines.brain import Brain
from pydantic import BaseModel

T = Any  # TypeVar placeholder for the mock


# ---- Mock LLM Gateway -------------------------------------------------------

class MockLLMGateway:
    """Deterministic mock that returns canned responses without calling any provider.

    Implements the full LLMGateway protocol. Embed returns constant-dimension
    vectors so memory registration + retrieval work in tests.
    """

    def __init__(self, *, embed_dim: int = 8) -> None:
        self.embed_dim = embed_dim
        self.call_log: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        stop: Sequence[str] | None = None,
    ) -> LLMResponse:
        self.call_log.append({"method": "complete", "role": role, "n_messages": len(messages)})
        return LLMResponse(
            text="Mocked LLM response.",
            model="mock-model",
            input_tokens=10,
            output_tokens=5,
            finish_reason="stop",
        )

    async def complete_structured(
        self,
        messages: Sequence[ChatMessage],
        schema: type[BaseModel],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> BaseModel:
        self.call_log.append({"method": "complete_structured", "role": role, "schema": schema.__name__})
        raise NotImplementedError("complete_structured mock needs per-test overrides")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self.call_log.append({"method": "stream", "role": role})
        yield "Mocked "
        yield "streamed "
        yield "response."

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        self.call_log.append({"method": "embed", "n_texts": len(texts)})
        import hashlib
        vectors = []
        for text in texts:
            h = hashlib.md5(text.encode()).digest()
            raw = [float(b) / 255.0 for b in h[: self.embed_dim]]
            while len(raw) < self.embed_dim:
                raw.append(0.0)
            vectors.append(raw[: self.embed_dim])
        return vectors


# ---- Fixtures ----------------------------------------------------------------

@pytest.fixture
def mock_llm() -> MockLLMGateway:
    """Fresh mock LLM gateway."""
    return MockLLMGateway()


@pytest.fixture
def settings() -> Settings:
    """Settings with all-default in-memory backends."""
    return Settings(
        SEMANTIC_MEMORY_BACKEND="inmemory",
        EPISODIC_MEMORY_BACKEND="inmemory",
        CROSSDOC_GRAPH_BACKEND="networkx",
    )


@pytest_asyncio.fixture
async def brain(mock_llm: MockLLMGateway, settings: Settings) -> Brain:
    """Fully wired Brain with mocked LLM and in-memory backends."""
    return Brain.build(llm=mock_llm, settings=settings)  # type: ignore[arg-type]


# ---- Factory helpers ---------------------------------------------------------

def make_document(
    *,
    project_id: str = "test-project",
    title: str = "Test Spec",
    kind: DocumentKind = DocumentKind.PDF,
) -> Document:
    return Document(
        id=f"doc_{uuid4().hex[:8]}",
        title=title,
        kind=kind,
        sha256="a" * 64,
        source_uri="/tmp/test.pdf",
        scope="project",
        project_id=project_id,
        page_count=10,
    )


def make_section(
    document_id: str,
    *,
    title: str = "Section 1",
    level: int = 1,
) -> Section:
    return Section(
        id=f"sec_{uuid4().hex[:8]}",
        document_id=document_id,
        number="1",
        title=title,
        level=level,
        page_start=1,
        page_end=5,
        char_start=0,
        char_end=500,
    )


def make_chunk(
    document_id: str,
    section_id: str | None = None,
    *,
    text: str = "The system shall respond within 200ms under normal load.",
    kind: ChunkKind = ChunkKind.PROSE,
) -> Chunk:
    return Chunk(
        id=f"ch_{uuid4().hex[:8]}",
        document_id=document_id,
        section_id=section_id,
        text=text,
        kind=kind,
        token_count=15,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(text),
    )


def make_requirement(
    project_id: str = "test-project",
    *,
    statement: str = "The system shall respond within 200ms under normal load.",
    source_chunk_ids: list[str] | None = None,
    source_document_id: str = "doc_test",
) -> Requirement:
    return Requirement(
        id=f"req_{uuid4().hex[:8]}",
        title="Performance requirement",
        kind=RequirementKind.FUNCTIONAL,
        statement=statement,
        priority=3,
        source_document_id=source_document_id,
        source_chunk_ids=source_chunk_ids or [],
        verbatim_excerpt=statement,
        project_id=project_id,
    )


def make_test_case(
    *,
    title: str = "Verify response time",
    requirement_ids: list[str] | None = None,
) -> TestCase:
    return TestCase(
        id=f"tc_{uuid4().hex[:8]}",
        title=title,
        objective="Verify the system meets the performance requirement.",
        steps=[
            TestStep(
                id=f"st_{uuid4().hex[:8]}",
                index=1,
                action="Send request",
                expected_result="Response within 200ms",
            ),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id=f"ac_{uuid4().hex[:8]}",
                statement="Response time < 200ms",
            ),
        ],
        requirement_ids=requirement_ids or [],
        risk_level=3,
        estimated_duration_minutes=30,
    )
