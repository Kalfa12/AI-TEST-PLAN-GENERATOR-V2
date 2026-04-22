"""Unit tests for Pydantic data models."""

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
from ai_testplan_generator.models.traceability import TraceKind, TraceLink


class TestDocumentModels:
    def test_document_creation(self):
        doc = Document(
            id="doc_001",
            title="SRS v3",
            kind=DocumentKind.PDF,
            sha256="a" * 64,
            source_uri="/tmp/srs.pdf",
            scope="project",
            project_id="proj-42",
            page_count=100,
        )
        assert doc.id == "doc_001"
        assert doc.kind == DocumentKind.PDF

    def test_document_json_roundtrip(self):
        doc = Document(
            id="doc_002",
            title="ISO Standard",
            kind=DocumentKind.PDF,
            sha256="b" * 64,
            source_uri="/tmp/iso.pdf",
            scope="general",
            page_count=50,
        )
        json_str = doc.model_dump_json()
        restored = Document.model_validate_json(json_str)
        assert restored.id == doc.id
        assert restored.scope == "general"

    def test_section_creation(self):
        sec = Section(
            id="sec_001",
            document_id="doc_001",
            number="3.2",
            title="Performance Requirements",
            level=2,
            page_start=15,
            page_end=20,
            char_start=1000,
            char_end=5000,
        )
        assert sec.level == 2
        assert sec.document_id == "doc_001"

    def test_chunk_creation(self):
        ch = Chunk(
            id="ch_001",
            document_id="doc_001",
            section_id="sec_001",
            text="The system shall...",
            kind=ChunkKind.PROSE,
            token_count=5,
            page_start=15,
            page_end=15,
            char_start=1000,
            char_end=1019,
        )
        assert ch.token_count == 5
        assert ch.kind == ChunkKind.PROSE


class TestRequirementModels:
    def test_requirement_creation(self):
        req = Requirement(
            id="req_001",
            title="Latency SLA",
            kind=RequirementKind.FUNCTIONAL,
            statement="Response time < 200ms",
            priority=4,
            source_document_id="doc_001",
            source_chunk_ids=["ch_001"],
            verbatim_excerpt="Response time shall not exceed 200ms",
            project_id="proj-42",
        )
        assert req.priority == 4
        assert len(req.source_chunk_ids) == 1

    def test_requirement_json_roundtrip(self):
        req = Requirement(
            id="req_002",
            title="Safety",
            kind=RequirementKind.SAFETY,
            statement="System shall be safe",
            priority=5,
            source_document_id="doc_001",
            source_chunk_ids=[],
            verbatim_excerpt="safe",
            project_id="proj-42",
        )
        json_str = req.model_dump_json()
        restored = Requirement.model_validate_json(json_str)
        assert restored.id == req.id


class TestTestArtifactModels:
    def test_test_case_creation(self):
        tc = TestCase(
            id="tc_001",
            title="Verify latency",
            objective="Verify the system meets SLA for latency.",
            steps=[
                TestStep(id="st_001", index=1, action="Send HTTP request", expected_result="Response < 200ms"),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac_001", statement="p99 < 200ms"),
            ],
            requirement_ids=["req_001"],
            risk_level=4,
            estimated_duration_minutes=60,
        )
        assert len(tc.steps) == 1
        assert tc.risk_level == 4

    def test_test_plan_creation(self):
        tc = TestCase(
            id="tc_001",
            title="Verify latency",
            objective="Verify system meets SLA.",
            steps=[],
            acceptance_criteria=[],
            requirement_ids=["req_001"],
            risk_level=3,
            estimated_duration_minutes=30,
        )
        plan = TestPlan(
            id="plan_001",
            title="Pump Controller Test Plan",
            detail_level=DetailLevel.DETAILED,
            scope="Full verification of SRS v3",
            strategy="Risk-based testing with performance emphasis",
            test_cases=[tc],
            coverage_matrix={"req_001": ["tc_001"]},
        )
        assert len(plan.test_cases) == 1
        assert plan.detail_level == DetailLevel.DETAILED

    def test_detail_level_enum(self):
        assert DetailLevel.SUMMARY == "summary"
        assert DetailLevel.DETAILED == "detailed"


class TestTraceability:
    def test_trace_link_creation(self):
        link = TraceLink(
            kind=TraceKind.COVERS,
            source_id="tc_001",
            source_type="TestCase",
            target_id="req_001",
            target_type="Requirement",
            confidence=0.95,
        )
        assert link.kind == TraceKind.COVERS
        assert link.id.startswith("tr_")

    def test_trace_kind_values(self):
        assert TraceKind.DERIVES_FROM == "derives_from"
        assert TraceKind.COVERS == "covers"
        assert TraceKind.REFINES == "refines"
        assert TraceKind.CONTRADICTS == "contradicts"
        assert TraceKind.DUPLICATES == "duplicates"
