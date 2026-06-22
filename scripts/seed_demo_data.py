"""Seed a realistic demo dataset without deleting non-demo user data.

Usage:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --db data/app.db

The script is intentionally idempotent. It removes the previous demo project
with the stable id DEMO_PROJECT_ID, then recreates it with documents,
requirements, resources, plans, test cases, audit events, and cost rows.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ai_testplan_generator.api.security.password import hash_password
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.artifacts import ArtifactRepository
from ai_testplan_generator.domain.projects import (
    Project,
    ProjectIndustry,
    ProjectRepository,
    ProjectRole,
)
from ai_testplan_generator.domain.users import UserRepository
from ai_testplan_generator.models import (
    AcceptanceCriterion,
    Chunk,
    ChunkKind,
    DetailLevel,
    Document,
    DocumentKind,
    Milestone,
    Requirement,
    RequirementKind,
    Resource,
    Section,
    SourceEvidence,
    TestCase,
    TestCaseStatus,
    TestPlan,
    TestSchedule,
    TestStep,
)
from ai_testplan_generator.models.planning import ScheduledAssignment


DEMO_PROJECT_ID = "proj_demo_sf_edge"
DEMO_PLAN_ID = "plan_demo_sf_edge_v1"
DEMO_SECOND_PLAN_ID = "plan_demo_security_focus"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "password123"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed demo data for AI Test Plan Generator.")
    parser.add_argument("--db", default=None, help="Defaults to APP_DB_PATH from settings.")
    parser.add_argument(
        "--admin-email",
        default=ADMIN_EMAIL,
        help="Admin/demo account email to create or reset.",
    )
    parser.add_argument(
        "--admin-password",
        default=ADMIN_PASSWORD,
        help="Password assigned to the admin/demo account.",
    )
    return parser


def _now(offset_minutes: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _count_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.25))


def _read_source(name: str) -> str:
    return (Path("docs/test-knowledge-base") / name).read_text(encoding="utf-8")


def _make_doc(
    *,
    id: str,
    title: str,
    filename: str,
    project_id: str,
    page_count: int,
) -> Document:
    pdf_path = Path("docs/test-knowledge-base/pdf") / filename.replace(".md", ".pdf")
    source = pdf_path if pdf_path.exists() else Path("docs/test-knowledge-base") / filename
    return Document(
        id=id,
        project_id=project_id,
        kind=DocumentKind.PDF if source.suffix == ".pdf" else DocumentKind.MARKDOWN,
        title=title,
        source_uri=str(source),
        sha256=_sha(source),
        ingested_at=_now(-90 + page_count),
        page_count=page_count,
        language="en",
        scope="project",
        metadata={
            "original_filename": source.name,
            "demo_seed": "true",
            "document_id": id,
        },
    )


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Document"


def _make_chunks(
    *,
    doc: Document,
    filename: str,
    section_id: str,
    max_chars: int = 1350,
) -> list[Chunk]:
    text = _read_source(filename)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    buf = ""
    char_start = 0
    chunk_index = 1
    for para in paras:
        if len(buf) + len(para) > max_chars and buf:
            ch_text = buf.strip()
            chunks.append(
                Chunk(
                    id=f"ch_{doc.id}_{chunk_index:02d}",
                    document_id=doc.id,
                    section_id=section_id,
                    kind=ChunkKind.PROSE,
                    text=ch_text,
                    token_count=_count_tokens(ch_text),
                    page_start=min(doc.page_count or 1, chunk_index),
                    page_end=min(doc.page_count or 1, chunk_index),
                    char_start=char_start,
                    char_end=char_start + len(ch_text),
                    extra={"demo_seed": True},
                )
            )
            char_start += len(ch_text) + 2
            chunk_index += 1
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf.strip():
        ch_text = buf.strip()
        chunks.append(
            Chunk(
                id=f"ch_{doc.id}_{chunk_index:02d}",
                document_id=doc.id,
                section_id=section_id,
                kind=ChunkKind.PROSE,
                text=ch_text,
                token_count=_count_tokens(ch_text),
                page_start=min(doc.page_count or 1, chunk_index),
                page_end=min(doc.page_count or 1, chunk_index),
                char_start=char_start,
                char_end=char_start + len(ch_text),
                extra={"demo_seed": True},
            )
        )
    return chunks


def _make_doc_bundle(project_id: str) -> tuple[list[Document], list[Section], list[Chunk]]:
    specs = [
        (
            "doc_demo_prd",
            "SF-EDGE Product Requirements Document",
            "01_SF-EDGE-PRD_product_requirements.md",
            4,
        ),
        (
            "doc_demo_arch",
            "SF-EDGE Architecture and API Specification",
            "02_SF-EDGE_architecture_and_api.md",
            5,
        ),
        (
            "doc_demo_sec",
            "SF-EDGE Security and Compliance Requirements",
            "03_SF-EDGE_security_and_compliance.md",
            4,
        ),
        (
            "doc_demo_val",
            "SF-EDGE Validation Strategy",
            "04_SF-EDGE_validation_strategy.md",
            4,
        ),
        (
            "doc_demo_ops",
            "SF-EDGE Incident and Change Log",
            "05_SF-EDGE_incident_and_change_log.md",
            4,
        ),
    ]
    docs: list[Document] = []
    sections: list[Section] = []
    chunks: list[Chunk] = []
    for doc_id, title, filename, pages in specs:
        doc = _make_doc(
            id=doc_id,
            title=title,
            filename=filename,
            project_id=project_id,
            page_count=pages,
        )
        source_text = _read_source(filename)
        section = Section(
            id=f"sec_{doc_id}_main",
            document_id=doc.id,
            number="1",
            title=_first_heading(source_text),
            level=1,
            char_start=0,
            char_end=len(source_text),
            page_start=1,
            page_end=pages,
        )
        docs.append(doc)
        sections.append(section)
        chunks.extend(_make_chunks(doc=doc, filename=filename, section_id=section.id))
    return docs, sections, chunks


def _req(
    *,
    id: str,
    external_id: str,
    kind: RequirementKind,
    title: str,
    statement: str,
    priority: int,
    doc: str,
    chunk: str,
    hint: str,
) -> Requirement:
    return Requirement(
        id=id,
        project_id=DEMO_PROJECT_ID,
        external_id=external_id,
        kind=kind,
        title=title,
        statement=statement,
        rationale="Demo requirement extracted from the SF-EDGE source corpus.",
        acceptance_hint=hint,
        priority=priority,
        source_document_id=doc,
        source_section_id=f"sec_{doc}_main",
        source_chunk_ids=[chunk],
        verbatim_excerpt=statement,
    )


def _requirements() -> list[Requirement]:
    return [
        _req(
            id="req_demo_device_registration",
            external_id="REQ-FUNC-001",
            kind=RequirementKind.FUNCTIONAL,
            title="Device registration",
            statement="The gateway shall allow a maintenance engineer to register a new industrial device with a unique device ID, protocol type, host, polling interval, and signal map.",
            priority=5,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_02",
            hint="Create valid and invalid device registration requests, including duplicate IDs.",
        ),
        _req(
            id="req_demo_protocol_support",
            external_id="REQ-FUNC-002",
            kind=RequirementKind.INTERFACE,
            title="Supported protocol validation",
            statement="The gateway shall support Modbus TCP, OPC UA, MQTT subscriber mode, and HTTP sensor adapter mode, with protocol-specific validation before saving a device.",
            priority=4,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_02",
            hint="Validate happy path and malformed configuration per protocol.",
        ),
        _req(
            id="req_demo_polling_interval",
            external_id="REQ-FUNC-003",
            kind=RequirementKind.PERFORMANCE,
            title="Telemetry polling interval",
            statement="The gateway shall collect telemetry according to each device polling interval and reject polling intervals below 1 second.",
            priority=4,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_02",
            hint="Use boundary values: 0, 1, and 10 seconds.",
        ),
        _req(
            id="req_demo_local_buffering",
            external_id="REQ-FUNC-004",
            kind=RequirementKind.RELIABILITY,
            title="Local buffering during cloud outage",
            statement="If the cloud connection is unavailable, the gateway shall buffer telemetry locally for at least 24 hours at a rate of 2,000 measurements per minute.",
            priority=5,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_03",
            hint="Simulate cloud outage and verify retained records and FIFO behavior.",
        ),
        _req(
            id="req_demo_duplicate_prevention",
            external_id="REQ-FUNC-005",
            kind=RequirementKind.RELIABILITY,
            title="Duplicate telemetry prevention",
            statement="When connectivity is restored, the gateway shall forward buffered telemetry in chronological order and shall not forward duplicate telemetry records.",
            priority=5,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_03",
            hint="Replay a partially accepted batch and verify stable event IDs prevent duplicates.",
        ),
        _req(
            id="req_demo_device_health",
            external_id="REQ-FUNC-006",
            kind=RequirementKind.OPERATIONAL,
            title="Device health status",
            statement="The gateway shall update device health status within 30 seconds after a communication failure is detected.",
            priority=5,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_04",
            hint="Disconnect protocol simulators and measure health transition time.",
        ),
        _req(
            id="req_demo_alerting",
            external_id="REQ-FUNC-007",
            kind=RequirementKind.OPERATIONAL,
            title="Operational alert triggers",
            statement="The gateway shall generate alerts for prolonged device disconnects, buffer capacity above 80 percent, repeated forwarding failures, and certificate expiration within 14 days.",
            priority=4,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_04",
            hint="Drive each threshold independently and confirm alert contents.",
        ),
        _req(
            id="req_demo_config_versioning",
            external_id="REQ-FUNC-008",
            kind=RequirementKind.FUNCTIONAL,
            title="Configuration versioning",
            statement="Every configuration update shall create a new immutable configuration version.",
            priority=4,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_04",
            hint="Apply multiple updates and verify immutable history.",
        ),
        _req(
            id="req_demo_rollback",
            external_id="REQ-FUNC-009",
            kind=RequirementKind.FUNCTIONAL,
            title="Configuration rollback",
            statement="The gateway shall allow a site administrator to roll back to the previous valid configuration version without deleting the failed version from audit history.",
            priority=4,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_04",
            hint="Perform valid update, invalid update, then rollback.",
        ),
        _req(
            id="req_demo_diagnostics_redaction",
            external_id="REQ-FUNC-010 / SEC-REQ-021",
            kind=RequirementKind.SECURITY,
            title="Diagnostic bundle redaction",
            statement="Diagnostic bundles shall include operational information while redacting passwords, API tokens, private keys, bearer tokens, and cloud endpoint credentials.",
            priority=5,
            doc="doc_demo_sec",
            chunk="ch_doc_demo_sec_03",
            hint="Seed nested secret-like values and verify they do not appear in exported diagnostics.",
        ),
        _req(
            id="req_demo_authentication",
            external_id="SEC-REQ-001",
            kind=RequirementKind.SECURITY,
            title="Authenticated API access",
            statement="All API endpoints except /health/live shall require authentication and unauthenticated requests shall return 401 Unauthorized.",
            priority=5,
            doc="doc_demo_sec",
            chunk="ch_doc_demo_sec_01",
            hint="Exercise authenticated and unauthenticated calls against representative endpoints.",
        ),
        _req(
            id="req_demo_rbac",
            external_id="SEC-REQ-010",
            kind=RequirementKind.SECURITY,
            title="Role-based access control",
            statement="The system shall enforce role-based access control for privileged operations such as device configuration, user management, rollback, and diagnostic access.",
            priority=5,
            doc="doc_demo_sec",
            chunk="ch_doc_demo_sec_02",
            hint="Verify each role can only perform its allowed actions.",
        ),
        _req(
            id="req_demo_support_grant",
            external_id="SEC-REQ-011",
            kind=RequirementKind.SECURITY,
            title="Temporary support grant",
            statement="A site administrator may create a temporary support grant that expires automatically after a maximum of 4 hours, is revocable, audited, and restricted to diagnostic data.",
            priority=3,
            doc="doc_demo_sec",
            chunk="ch_doc_demo_sec_02",
            hint="Create, revoke, and let a support grant expire.",
        ),
        _req(
            id="req_demo_tls_validation",
            external_id="SEC-REQ-042",
            kind=RequirementKind.SECURITY,
            title="Cloud endpoint certificate validation",
            statement="The Cloud Forwarder shall validate the cloud endpoint certificate chain before sending telemetry; if validation fails, telemetry shall remain buffered locally.",
            priority=4,
            doc="doc_demo_sec",
            chunk="ch_doc_demo_sec_04",
            hint="Use invalid cloud certificate and verify forwarding stops while buffering continues.",
        ),
        _req(
            id="req_demo_startup_time",
            external_id="REQ-NFR-001",
            kind=RequirementKind.PERFORMANCE,
            title="Startup readiness",
            statement="After power-on, the gateway shall be ready to collect telemetry within 90 seconds.",
            priority=3,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_05",
            hint="Power-cycle the gateway and measure readiness.",
        ),
        _req(
            id="req_demo_30_day_operation",
            external_id="REQ-NFR-002",
            kind=RequirementKind.RELIABILITY,
            title="Continuous operation",
            statement="The gateway software shall support continuous operation for at least 30 days without manual restart under nominal load.",
            priority=3,
            doc="doc_demo_prd",
            chunk="ch_doc_demo_prd_05",
            hint="Use long-run or compressed endurance profile.",
        ),
    ]


def _tc(
    *,
    id: str,
    title: str,
    objective: str,
    req_ids: list[str],
    risk: int,
    assignee: str,
    status: TestCaseStatus,
    evidence_doc: str,
    evidence_chunk: str,
    duration: int,
    types: list[str],
) -> TestCase:
    return TestCase(
        id=id,
        title=title,
        objective=objective,
        testing_types=types,
        preconditions=[
            "Reference gateway is powered and reachable.",
            "Test user has the required project role.",
            "Simulators and cloud ingestion endpoint are running.",
        ],
        equipment=[
            "SF-EDGE reference gateway",
            "Modbus/OPC UA/MQTT/HTTP simulators",
            "Cloud ingestion simulator",
            "Log and metrics collector",
        ],
        setup="Load the demo SF-EDGE configuration and reset telemetry buffers before execution.",
        steps=[
            TestStep(
                id=f"st_{id}_01",
                index=1,
                action="Prepare the gateway, simulator, and API client for the target scenario.",
                expected_result="All services report healthy status before the test starts.",
            ),
            TestStep(
                id=f"st_{id}_02",
                index=2,
                action="Execute the scenario using the documented API or simulator action.",
                expected_result="The gateway accepts valid operations and rejects invalid operations according to the requirement.",
            ),
            TestStep(
                id=f"st_{id}_03",
                index=3,
                action="Collect logs, API responses, metrics, and persisted records.",
                expected_result="Evidence is complete and traceable to the requirement IDs.",
            ),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id=f"ac_{id}_01",
                statement="Observed behavior matches the requirement without critical errors.",
                measurable=True,
            ),
            AcceptanceCriterion(
                id=f"ac_{id}_02",
                statement="Audit or telemetry evidence is available for review.",
                measurable=True,
            ),
        ],
        teardown="Reset simulators and archive collected logs.",
        requirement_ids=req_ids,
        estimated_duration_minutes=duration,
        risk_level=risk,
        risk_description="High priority scenario for release confidence."
        if risk >= 4
        else "Standard validation scenario.",
        deliverables=["Execution log", "Screenshots or API transcript", "Traceability evidence"],
        dependencies=["Gateway demo configuration", "Simulation environment"],
        kpis=["Pass/fail result", "Response time", "Audit completeness"],
        assignee=assignee,
        status=status,
        status_note="Seeded demo status.",
        tags=["demo", "sf-edge"],
        source_evidence=[
            SourceEvidence(
                chunk_id=evidence_chunk,
                document_id=evidence_doc,
                page_start=1,
                page_end=2,
                excerpt="Seeded from SF-EDGE demo corpus.",
            )
        ],
    )


def _test_cases() -> list[TestCase]:
    return [
        _tc(
            id="tc_demo_device_registration",
            title="Register valid and duplicate industrial devices",
            objective="Verify device registration validation, duplicate rejection, and audit logging.",
            req_ids=["req_demo_device_registration", "req_demo_protocol_support"],
            risk=4,
            assignee="Nadia QA",
            status=TestCaseStatus.PLANNED,
            evidence_doc="doc_demo_prd",
            evidence_chunk="ch_doc_demo_prd_02",
            duration=35,
            types=["functional", "api", "audit"],
        ),
        _tc(
            id="tc_demo_polling_boundary",
            title="Validate telemetry polling interval boundaries",
            objective="Verify that 1 second is accepted and values below 1 second are rejected.",
            req_ids=["req_demo_polling_interval"],
            risk=3,
            assignee="Amine QA",
            status=TestCaseStatus.PASSED,
            evidence_doc="doc_demo_prd",
            evidence_chunk="ch_doc_demo_prd_02",
            duration=25,
            types=["functional", "boundary"],
        ),
        _tc(
            id="tc_demo_cloud_outage_buffering",
            title="Buffer telemetry during two-hour cloud outage",
            objective="Verify local buffering while cloud connectivity is unavailable.",
            req_ids=["req_demo_local_buffering"],
            risk=5,
            assignee="Youssef Systems",
            status=TestCaseStatus.RUNNING,
            evidence_doc="doc_demo_val",
            evidence_chunk="ch_doc_demo_val_02",
            duration=120,
            types=["integration", "reliability", "stress"],
        ),
        _tc(
            id="tc_demo_duplicate_prevention",
            title="Prevent duplicate forwarding after transient timeout",
            objective="Replay buffered telemetry after a partial cloud timeout and verify no duplicate records are accepted.",
            req_ids=["req_demo_duplicate_prevention"],
            risk=5,
            assignee="Youssef Systems",
            status=TestCaseStatus.PLANNED,
            evidence_doc="doc_demo_ops",
            evidence_chunk="ch_doc_demo_ops_02",
            duration=60,
            types=["integration", "regression"],
        ),
        _tc(
            id="tc_demo_device_health_disconnect",
            title="Detect device disconnect within timing limit",
            objective="Verify device health status changes within 30 seconds after communication failure.",
            req_ids=["req_demo_device_health", "req_demo_alerting"],
            risk=4,
            assignee="Nadia QA",
            status=TestCaseStatus.BLOCKED,
            evidence_doc="doc_demo_ops",
            evidence_chunk="ch_doc_demo_ops_04",
            duration=45,
            types=["system", "operational"],
        ),
        _tc(
            id="tc_demo_config_rollback",
            title="Version and rollback gateway configuration",
            objective="Verify immutable configuration versions and rollback behavior.",
            req_ids=["req_demo_config_versioning", "req_demo_rollback"],
            risk=4,
            assignee="Amine QA",
            status=TestCaseStatus.PLANNED,
            evidence_doc="doc_demo_val",
            evidence_chunk="ch_doc_demo_val_03",
            duration=50,
            types=["functional", "audit"],
        ),
        _tc(
            id="tc_demo_diagnostic_redaction",
            title="Redact secrets from diagnostic bundle",
            objective="Verify recursive redaction of passwords, tokens, private keys, and cloud credentials.",
            req_ids=["req_demo_diagnostics_redaction"],
            risk=5,
            assignee="Cybersecurity Lead",
            status=TestCaseStatus.FAILED,
            evidence_doc="doc_demo_ops",
            evidence_chunk="ch_doc_demo_ops_03",
            duration=40,
            types=["security", "regression"],
        ),
        _tc(
            id="tc_demo_rbac_matrix",
            title="Verify role-based permissions",
            objective="Verify that each project role can only execute allowed privileged actions.",
            req_ids=["req_demo_authentication", "req_demo_rbac"],
            risk=5,
            assignee="Cybersecurity Lead",
            status=TestCaseStatus.PLANNED,
            evidence_doc="doc_demo_sec",
            evidence_chunk="ch_doc_demo_sec_02",
            duration=55,
            types=["security", "api"],
        ),
        _tc(
            id="tc_demo_support_grant",
            title="Validate support grant lifecycle",
            objective="Verify support grant creation, revocation, automatic expiration, and audit logging.",
            req_ids=["req_demo_support_grant"],
            risk=3,
            assignee="Cybersecurity Lead",
            status=TestCaseStatus.NOT_STARTED,
            evidence_doc="doc_demo_sec",
            evidence_chunk="ch_doc_demo_sec_02",
            duration=35,
            types=["security", "workflow"],
        ),
        _tc(
            id="tc_demo_tls_validation",
            title="Reject invalid cloud TLS certificate",
            objective="Verify telemetry remains buffered when cloud certificate validation fails.",
            req_ids=["req_demo_tls_validation"],
            risk=4,
            assignee="Youssef Systems",
            status=TestCaseStatus.PLANNED,
            evidence_doc="doc_demo_sec",
            evidence_chunk="ch_doc_demo_sec_04",
            duration=40,
            types=["security", "integration"],
        ),
    ]


def _schedule(plan_id: str, test_cases: list[TestCase], resources: list[Resource]) -> TestSchedule:
    base = date.today() + timedelta(days=1)
    res_by_role = {r.role: r.id for r in resources if r.role}
    assignments: dict[str, ScheduledAssignment] = {}
    for index, tc in enumerate(test_cases):
        start = base + timedelta(days=index // 2)
        end = start + timedelta(days=1 if tc.risk_level >= 5 else 0)
        role = "Security Engineer" if "security" in tc.testing_types else "QA Engineer"
        resource_id = res_by_role.get(role) or resources[0].id
        assignments[tc.id] = ScheduledAssignment(
            start=start,
            end=end,
            resource_ids=[resource_id],
            service="Validation Lab",
        )
    return TestSchedule(
        plan_id=plan_id,
        milestones=[
            Milestone(id="ms_demo_env_ready", name="Environment ready", due=base, gate=True),
            Milestone(
                id="ms_demo_security_review",
                name="Security evidence review",
                due=base + timedelta(days=4),
                gate=True,
            ),
            Milestone(
                id="ms_demo_release_review",
                name="Release readiness review",
                due=base + timedelta(days=7),
                gate=True,
                depends_on=["ms_demo_security_review"],
            ),
        ],
        assignments=assignments,
    )


def _plan(resources: list[Resource]) -> TestPlan:
    cases = _test_cases()
    coverage: dict[str, list[str]] = {req.id: [] for req in _requirements()}
    for tc in cases:
        for req_id in tc.requirement_ids:
            coverage.setdefault(req_id, []).append(tc.id)
    return TestPlan(
        id=DEMO_PLAN_ID,
        project_id=DEMO_PROJECT_ID,
        title="SF-EDGE Gateway Validation Plan - Release Candidate 1",
        version="v1.0-demo",
        author="AI Test Plan Generator",
        detail_level=DetailLevel.DETAILED,
        introduction=(
            "This demo plan validates the Smart Factory Edge Gateway across "
            "telemetry collection, local buffering, cloud forwarding, security, "
            "auditability, and operational readiness."
        ),
        objectives=[
            "Demonstrate traceability from source documents to requirements and tests.",
            "Validate the highest-risk reliability and security requirements.",
            "Provide a reviewable release-candidate test package for QA.",
        ],
        scope=(
            "Version 1 SF-EDGE gateway behavior using simulated Modbus, OPC UA, "
            "MQTT, HTTP sensor, and cloud ingestion endpoints."
        ),
        out_of_scope=[
            "Edge machine-learning inference",
            "PLC firmware updates",
            "Multi-site orchestration",
            "Mobile application workflows",
        ],
        strategy=(
            "Use a risk-based strategy. High-priority requirements receive "
            "integration or security tests. Medium-priority requirements receive "
            "functional or workflow coverage. Known incidents drive regression tests."
        ),
        entry_criteria=[
            "Reference gateway hardware is available.",
            "Simulators for all supported protocols are running.",
            "Test users and roles are configured.",
            "Logging and metrics capture are enabled.",
        ],
        exit_criteria=[
            "All critical and high-priority tests are passed or dispositioned.",
            "No open critical defect remains.",
            "Traceability matrix has been reviewed.",
            "Diagnostic redaction evidence is archived.",
        ],
        risks=[
            "Cloud outage scenarios may require long execution windows.",
            "OPC UA health timing is currently affected by an open issue.",
            "Diagnostic redaction must be carefully retested after every logging change.",
        ],
        test_cases=cases,
        coverage_matrix=coverage,
        schedule=_schedule(DEMO_PLAN_ID, cases, resources),
    )


def _second_plan() -> TestPlan:
    cases = [
        tc
        for tc in _test_cases()
        if any(req in tc.requirement_ids for req in [
            "req_demo_authentication",
            "req_demo_rbac",
            "req_demo_diagnostics_redaction",
            "req_demo_tls_validation",
            "req_demo_support_grant",
        ])
    ]
    coverage: dict[str, list[str]] = {req.id: [] for req in _requirements()}
    for tc in cases:
        for req_id in tc.requirement_ids:
            coverage.setdefault(req_id, []).append(tc.id)
    return TestPlan(
        id=DEMO_SECOND_PLAN_ID,
        project_id=DEMO_PROJECT_ID,
        title="SF-EDGE Security Regression Pack",
        version="v0.3-demo",
        author="AI Test Plan Generator",
        detail_level=DetailLevel.SUMMARY,
        introduction="Focused regression pack for authentication, RBAC, diagnostics, support grants, and TLS validation.",
        objectives=["Exercise security controls before release review."],
        scope="Security-sensitive API and diagnostic workflows.",
        strategy="Prioritize negative testing and audit evidence.",
        entry_criteria=["Security test accounts exist.", "Diagnostic bundle fixture includes known secret patterns."],
        exit_criteria=["No critical security regression remains.", "Audit evidence is attached."],
        risks=["False positives in redaction checks may require manual review."],
        test_cases=cases,
        coverage_matrix=coverage,
    )


def _resources() -> list[Resource]:
    return [
        Resource(
            id="res_demo_nadia",
            project_id=DEMO_PROJECT_ID,
            name="Nadia Benali",
            service="QA Validation",
            role="QA Engineer",
            availability_pct=80,
        ),
        Resource(
            id="res_demo_youssef",
            project_id=DEMO_PROJECT_ID,
            name="Youssef El Idrissi",
            service="Systems Lab",
            role="Systems Engineer",
            availability_pct=60,
        ),
        Resource(
            id="res_demo_cyber",
            project_id=DEMO_PROJECT_ID,
            name="Cybersecurity Reviewer",
            service="Security Office",
            role="Security Engineer",
            availability_pct=50,
        ),
        Resource(
            id="res_demo_lab",
            project_id=DEMO_PROJECT_ID,
            name="Industrial Gateway Bench",
            service="Validation Lab",
            role="Test Bench",
            availability_pct=100,
        ),
    ]


async def _ensure_admin(db_path: str, email: str, password: str) -> str:
    repo = await UserRepository.create(db_path=db_path)
    try:
        existing = await repo.get_by_email(email)
        password_hash = hash_password(password)
        if existing is None:
            user = await repo.create_user(
                email=email,
                display_name="Admin",
                password_hash=password_hash,
                is_admin=True,
            )
            return user.id
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                UPDATE users
                SET password_hash=?, disabled_at=NULL, is_admin=1, display_name=?
                WHERE id=?
                """,
                (password_hash, existing.display_name or "Admin", existing.id),
            )
            conn.commit()
        finally:
            conn.close()
        return existing.id
    finally:
        await repo.close()


async def _delete_previous_demo(project_repo: ProjectRepository, artifact_repo: ArtifactRepository) -> None:
    await artifact_repo.delete_project(DEMO_PROJECT_ID)
    await project_repo.delete_project(DEMO_PROJECT_ID)


def _insert_project_direct(db_path: str, project: Project) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects
                (id, name, description, industry, owner_id, created_at,
                 archived_at, monthly_budget_usd, budget_override_until, budget_override_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.name,
                project.description,
                project.industry.value,
                project.owner_id,
                project.created_at.isoformat(),
                project.archived_at.isoformat() if project.archived_at else None,
                project.monthly_budget_usd,
                project.budget_override_until.isoformat()
                if project.budget_override_until else None,
                project.budget_override_usd,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_llm_usage(db_path: str, *, project_id: str, user_id: str) -> None:
    migration = Path("src/ai_testplan_generator/memory/backends/migrations/004_llm_usage.sql")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute("DELETE FROM llm_usage WHERE project_id=?", (project_id,))
        rows = [
            ("Document Analyst", "deepseek/deepseek-chat", 18420, 2200, 0.018),
            ("Requirement Extractor", "deepseek/deepseek-chat", 26100, 5400, 0.031),
            ("Requirement Reviewer", "deepseek/deepseek-chat", 11800, 1600, 0.012),
            ("Test Architect", "deepseek/deepseek-chat", 9200, 1800, 0.010),
            ("Test Generator", "deepseek/deepseek-chat", 33750, 8400, 0.045),
            ("Traceability Agent", "deepseek/deepseek-chat", 6400, 900, 0.007),
            ("Copilot Agent", "deepseek/deepseek-chat", 4200, 1100, 0.005),
        ]
        for i, (agent, model, inp, out, cost) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO llm_usage
                    (ts, session_id, project_id, user_id, model, role,
                     input_tokens, output_tokens, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (_now(-70 + i * 8)).isoformat(),
                    "sess_demo_seed",
                    project_id,
                    user_id,
                    model,
                    agent,
                    inp,
                    out,
                    cost,
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def _seed(db_path: str, admin_email: str, admin_password: str) -> dict[str, int | str]:
    admin_id = await _ensure_admin(db_path, admin_email, admin_password)
    project_repo = await ProjectRepository.create(db_path=db_path)
    artifact_repo = await ArtifactRepository.create(db_path=db_path)
    try:
        await _delete_previous_demo(project_repo, artifact_repo)

        project = Project(
            id=DEMO_PROJECT_ID,
            name="DEMO - SF-EDGE Industrial Gateway",
            description=(
                "Demo project populated with realistic IoT gateway requirements, "
                "documents, plans, resources, coverage, and incidents."
            ),
            industry=ProjectIndustry.ENERGY,
            owner_id=admin_id,
            created_at=_now(),
            monthly_budget_usd=25.0,
        )
        _insert_project_direct(db_path, project)
        await project_repo.add_member(DEMO_PROJECT_ID, admin_id, ProjectRole.OWNER)

        docs, sections, chunks = _make_doc_bundle(DEMO_PROJECT_ID)
        for doc in docs:
            await artifact_repo.save_document(doc)
        await artifact_repo.save_sections(sections)
        await artifact_repo.save_chunks(chunks)

        reqs = _requirements()
        await artifact_repo.save_requirements(reqs)

        resources = _resources()
        for resource in resources:
            await artifact_repo.save_resource(resource)

        plan = _plan(resources)
        await artifact_repo.save_test_plan(plan)
        second_plan = _second_plan()
        await artifact_repo.save_test_plan(second_plan)

        for action, target_type, target_id, status in [
            ("DEMO_SEED:project_created", "project", DEMO_PROJECT_ID, 201),
            ("DOCUMENT_UPLOAD:demo_corpus", "document", "doc_demo_prd", 200),
            ("PLAN_GENERATION:demo_seed", "plan", DEMO_PLAN_ID, 200),
            ("CHAT_CONTEXT:demo_seed", "project", DEMO_PROJECT_ID, 200),
        ]:
            await artifact_repo.record_audit_event(
                user_id=admin_id,
                project_id=DEMO_PROJECT_ID,
                action=action,
                target_type=target_type,
                target_id=target_id,
                status=status,
                metadata={"demo_seed": True},
            )

        _insert_llm_usage(db_path, project_id=DEMO_PROJECT_ID, user_id=admin_id)
        return {
            "admin_id": admin_id,
            "project_id": DEMO_PROJECT_ID,
            "documents": len(docs),
            "chunks": len(chunks),
            "requirements": len(reqs),
            "resources": len(resources),
            "plans": 2,
            "test_cases": len(plan.test_cases),
        }
    finally:
        await artifact_repo.close()
        await project_repo.close()


async def _main() -> int:
    args = _parser().parse_args()
    db_path = args.db or Settings().app_db_path
    result = await _seed(db_path, args.admin_email, args.admin_password)
    print("Demo database seeded successfully.")
    for key, value in result.items():
        print(f"{key}: {value}")
    print(f"login: {args.admin_email} / {args.admin_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
