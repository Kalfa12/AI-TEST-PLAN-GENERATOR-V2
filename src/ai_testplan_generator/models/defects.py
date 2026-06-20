"""Defect taxonomy for requirements and test plans.

Single source of truth for the ~37 defect classes derived from
ISO/IEC/IEEE 29148, ISO/IEC/IEEE 29119, INCOSE GtWR, NASA SE Handbook,
DO-178C, and ISO 26262. Static checkers, the LLM reviewer prompts, the
aggregator, the API, and the UI all key off the IDs in `DefectType`.

The catalog itself (`CATALOG`) carries metadata only — definitions,
default severities, and standard references — not the detection logic.
Detectors live in `ai_testplan_generator.quality`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "major", "minor"]
DetectionDifficulty = Literal["mechanical", "llm", "domain_expert"]
TargetKind = Literal["requirement", "test_case", "test_plan"]
Detector = Literal["static", "reviewer", "requirement_reviewer", "traceability"]
DefectCategory = Literal["requirement", "test_plan"]
Industry = Literal["generic", "aerospace", "automotive", "medical", "energy"]


class DefectType(StrEnum):
    # --- Requirement defects ------------------------------------------------
    AMBIGUITY_LEXICAL = "ambiguity_lexical"
    AMBIGUITY_SYNTACTIC = "ambiguity_syntactic"
    AMBIGUITY_SEMANTIC = "ambiguity_semantic"
    AMBIGUITY_REFERENTIAL = "ambiguity_referential"
    COMPOUND_REQUIREMENT = "compound_requirement"
    CORRECTNESS_VS_SCOPE = "correctness_vs_scope"
    DEAD_REQUIREMENT = "dead_requirement"
    GRANULARITY_ISSUE = "granularity_issue"
    IMPLEMENTATION_BIAS = "implementation_bias"
    INCONSISTENCY_INTER_DOC = "inconsistency_inter_doc"
    INCONSISTENCY_INTRA_DOC = "inconsistency_intra_doc"
    MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"
    MISSING_RATIONALE = "missing_rationale"
    MODALITY_DRIFT = "modality_drift"
    OFF_STATED_RATIONALE = "off_stated_rationale"
    PLURALITY_ISSUE = "plurality_issue"
    PRONOUN_REFERENCE = "pronoun_reference"
    REDUNDANT_REQUIREMENT = "redundant_requirement"
    SUBJECTIVE_WORDING = "subjective_wording"
    TBD_PLACEHOLDER = "tbd_placeholder"
    TEMPORAL_AMBIGUITY = "temporal_ambiguity"
    TRACEABILITY_GAP = "traceability_gap"
    UNBOUNDED_ENUMERATION = "unbounded_enumeration"
    UNIVERSAL_QUALIFIER_MISUSE = "universal_qualifier_misuse"
    UNVERIFIABLE_PHRASING = "unverifiable_phrasing"
    VAGUE_MODIFIERS = "vague_modifiers"

    # --- Test plan defects --------------------------------------------------
    AMBIGUOUS_EXPECTED_RESULTS = "ambiguous_expected_results"
    FABRICATED_REQ_ID = "fabricated_req_id"
    COVERAGE_GAP = "coverage_gap"
    INCORRECT_ACCEPTANCE_CRITERIA = "incorrect_acceptance_criteria"
    MISSING_ENTRY_EXIT_CRITERIA = "missing_entry_exit_criteria"
    MISSING_RISK_ANALYSIS = "missing_risk_analysis"
    MISSING_TEARDOWN_CLEANUP = "missing_teardown_cleanup"
    REDUNDANT_COVERAGE = "redundant_coverage"
    SCHEMA_INCOMPLETE_FIELDS = "schema_incomplete_fields"
    SEVERITY_PRIORITY_CONFUSION = "severity_priority_confusion"
    UNRUNNABLE_PRECONDITIONS = "unrunnable_preconditions"
    UNTRACEABLE_TEST_CASE = "untraceable_test_case"


class DefectCatalogEntry(BaseModel):
    """Static metadata for one defect class."""

    model_config = ConfigDict(frozen=True)

    id: DefectType
    name: str
    category: DefectCategory
    default_severity: Severity
    detection_difficulty: DetectionDifficulty
    standard_refs: list[str]
    description: str
    example: str | None = None
    corrected_example: str | None = None


def _e(
    id: DefectType,
    name: str,
    category: DefectCategory,
    default_severity: Severity,
    detection_difficulty: DetectionDifficulty,
    standard_refs: list[str],
    description: str,
    example: str | None = None,
    corrected_example: str | None = None,
) -> tuple[DefectType, DefectCatalogEntry]:
    return id, DefectCatalogEntry(
        id=id,
        name=name,
        category=category,
        default_severity=default_severity,
        detection_difficulty=detection_difficulty,
        standard_refs=standard_refs,
        description=description,
        example=example,
        corrected_example=corrected_example,
    )


CATALOG: dict[DefectType, DefectCatalogEntry] = dict(
    [
        _e(
            DefectType.AMBIGUITY_LEXICAL,
            "Lexical ambiguity",
            "requirement",
            "major",
            "llm",
            ["ISO 29148:5.2.5", "INCOSE GtWR C3/R1"],
            "A word or phrase has multiple plausible interpretations because it is imprecise or undefined.",
            "The system shall log data at high speed.",
            "The system shall log data at a minimum rate of 1000 records per second.",
        ),
        _e(
            DefectType.AMBIGUITY_SYNTACTIC,
            "Syntactic ambiguity",
            "requirement",
            "major",
            "llm",
            ["INCOSE GtWR C3/R11", "EARS Ruleset"],
            "Sentence structure permits multiple logical parses (dangling modifiers, scope of conjunctions, etc.).",
            "The system shall notify the pilot and the copilot if available.",
            "When the copilot is available, the system shall notify the pilot and the copilot.",
        ),
        _e(
            DefectType.AMBIGUITY_SEMANTIC,
            "Semantic ambiguity",
            "requirement",
            "critical",
            "llm",
            ["ISO 29148:5.2.5", "INCOSE GtWR C11/R15"],
            "The requirement contains logically conflicting or impossible propositions within one statement.",
            "The valve shall remain closed while simultaneously venting pressure.",
            "While in the overpressure state, the system shall vent pressure through the secondary relief valve.",
        ),
        _e(
            DefectType.AMBIGUITY_REFERENTIAL,
            "Referential ambiguity",
            "requirement",
            "major",
            "llm",
            ["INCOSE GtWR C3/R18"],
            "Pronouns or references point to an unclear or multiple possible antecedents.",
            "The system shall activate the alarm when it detects an anomaly.",
            "The fire detection module shall activate the fire alarm when the module detects a temperature anomaly.",
        ),
        _e(
            DefectType.COMPOUND_REQUIREMENT,
            "Compound requirement",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:5.4.1", "INCOSE GtWR R18"],
            "A single requirement statement combines multiple distinct obligations that should be separated.",
            "The system shall log user activity and notify the administrator if unauthorized access is detected.",
            "1) The system shall log all user activity. 2) The system shall notify the administrator if unauthorized access is detected.",
        ),
        _e(
            DefectType.CORRECTNESS_VS_SCOPE,
            "Correctness vs scope",
            "requirement",
            "major",
            "domain_expert",
            ["ISO 29148:6.4.3", "INCOSE GtWR 4.3"],
            "Requirement is correctly written but applies to the wrong system boundary or document tier.",
        ),
        _e(
            DefectType.DEAD_REQUIREMENT,
            "Dead requirement",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:7.4.3.3", "DO-178C 5.1.1"],
            "A requirement that is not covered by any test case or design element (orphan).",
        ),
        _e(
            DefectType.GRANULARITY_ISSUE,
            "Granularity issue",
            "requirement",
            "major",
            "llm",
            ["DO-178C 5.1", "ISO 26262-6"],
            "Requirement stated at a level of detail inappropriate for its specification tier.",
        ),
        _e(
            DefectType.IMPLEMENTATION_BIAS,
            "Implementation bias",
            "requirement",
            "major",
            "llm",
            ["ISO 29148:5.3.2", "INCOSE GtWR C1", "DO-178C §3/§6"],
            "Requirement prescribes a specific solution or design choice rather than the behaviour to achieve.",
            "The system shall use a JSON-based protocol over HTTP for all data exchanges.",
            "The system shall support reliable data exchange between components with integrity and delivery guarantees.",
        ),
        _e(
            DefectType.INCONSISTENCY_INTER_DOC,
            "Inter-document inconsistency",
            "requirement",
            "critical",
            "domain_expert",
            ["ISO 29148:7.4.4", "DO-178C 2.4.5.1", "ISO 26262-3:8.4.4"],
            "Two related documents contain conflicting statements about the same item.",
        ),
        _e(
            DefectType.INCONSISTENCY_INTRA_DOC,
            "Intra-document inconsistency",
            "requirement",
            "critical",
            "llm",
            ["ISO 29148:5.4.2", "DO-178C 2.4.1", "ISO 26262-3:7.4"],
            "Two statements within the same document conflict or contradict each other.",
        ),
        _e(
            DefectType.MISSING_ACCEPTANCE_CRITERIA,
            "Missing acceptance criteria",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:6.5.2.2", "DO-178C 6.4.2", "ISO 26262-3:7.4"],
            "Requirement defines a behaviour but lacks measurable pass/fail conditions.",
            "The system shall provide secure user access.",
            "The system shall provide secure user access, verified by successful authentication using encrypted credentials with a failure rate below 0.1%.",
        ),
        _e(
            DefectType.MISSING_RATIONALE,
            "Missing rationale",
            "requirement",
            "minor",
            "mechanical",
            ["ISO 29148:5.3.4.2", "INCOSE GtWR C2"],
            "Requirement lacks an explanation of why it exists, hindering impact analysis and downstream tracing.",
        ),
        _e(
            DefectType.MODALITY_DRIFT,
            "Modality drift",
            "requirement",
            "minor",
            "mechanical",
            ["ISO 29148:5.2.7", "NASA TRC-M360"],
            "Use of non-binding modal verbs (should/may/will/must) where 'shall' is required, or inconsistent voice within a requirement.",
            "The system should log errors to the console.",
            "The system shall log errors to the console.",
        ),
        _e(
            DefectType.OFF_STATED_RATIONALE,
            "Off-stated rationale",
            "requirement",
            "major",
            "llm",
            ["ISO 29148:6.3.2.4", "INCOSE GtWR R1"],
            "Stated rationale does not actually justify the requirement, or hides a normative obligation inside descriptive text.",
        ),
        _e(
            DefectType.PLURALITY_ISSUE,
            "Plurality issue",
            "requirement",
            "minor",
            "llm",
            ["ISO 29148:5.4.2", "INCOSE GtWR 4.1.2"],
            "Inconsistent or ambiguous singular/plural usage that obscures whether one or many instances are meant.",
        ),
        _e(
            DefectType.PRONOUN_REFERENCE,
            "Pronoun reference",
            "requirement",
            "minor",
            "mechanical",
            ["ISO 29148:6.3.2.4", "INCOSE GtWR R18"],
            "A pronoun lacks a clear, singular, proximal antecedent.",
            "The system shall monitor the engine and activate the alarm if it fails.",
            "The system shall monitor the engine and activate the alarm if the engine fails.",
        ),
        _e(
            DefectType.REDUNDANT_REQUIREMENT,
            "Redundant requirement",
            "requirement",
            "minor",
            "llm",
            ["ISO 29148:5.4.3.2", "INCOSE GtWR 3.2.4"],
            "Two or more requirements convey the same obligation with different wording.",
        ),
        _e(
            DefectType.SUBJECTIVE_WORDING,
            "Subjective wording",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:5.4.2.3", "INCOSE GtWR (Ambiguity)"],
            "Opinion-based terms ('user-friendly', 'pleasant') that lack objective verification criteria.",
        ),
        _e(
            DefectType.TBD_PLACEHOLDER,
            "TBD/TBR placeholder",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:5.3.2.1", "NASA SE Table 4.2-1"],
            "Unresolved 'To Be Determined' or 'To Be Resolved' placeholder appears where a concrete value should be.",
            "The system shall respond to emergency shutdown commands within TBD seconds.",
            "The system shall respond to emergency shutdown commands within 2 seconds.",
        ),
        _e(
            DefectType.TEMPORAL_AMBIGUITY,
            "Temporal ambiguity",
            "requirement",
            "major",
            "llm",
            ["ISO 29148:5.4.2", "INCOSE GtWR C3", "EARS event-driven"],
            "Timing, ordering, or frequency stated without precise quantitative bounds.",
            "The system shall alert the operator immediately when a fault occurs.",
            "The system shall alert the operator within 2 seconds after a fault occurs.",
        ),
        _e(
            DefectType.TRACEABILITY_GAP,
            "Traceability gap",
            "requirement",
            "critical",
            "mechanical",
            ["ISO 29148:5.5.3.4", "DO-178C 6.4.3.1", "ISO 26262-6 §9"],
            "Requirement is missing an upward link to a parent need or downward link to design/tests.",
        ),
        _e(
            DefectType.UNBOUNDED_ENUMERATION,
            "Unbounded enumeration",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:6.4.3.2", "INCOSE GtWR 4.7"],
            "List of items ends with 'etc.', 'including but not limited to', etc., leaving the scope open.",
            "Supported formats include PDF, XML, etc.",
            "Supported formats shall be limited to PDF (v1.4) and XML (v1.0).",
        ),
        _e(
            DefectType.UNIVERSAL_QUALIFIER_MISUSE,
            "Universal qualifier misuse",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:7.4.2.1", "INCOSE GtWR 3.3.2", "NASA SP-2016-6105 3.2.2"],
            "Absolute quantifiers (all/always/never/every/100%) used without scope, creating unverifiable claims.",
            "The system shall never crash.",
            "The system shall achieve an MTBF of 10,000 hours.",
        ),
        _e(
            DefectType.UNVERIFIABLE_PHRASING,
            "Unverifiable phrasing",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:6.4.2.2", "INCOSE GtWR 5.2.2", "DO-178C 5.4.1.2"],
            "Requirement uses qualitative language that cannot be objectively measured or tested.",
        ),
        _e(
            DefectType.VAGUE_MODIFIERS,
            "Vague modifiers",
            "requirement",
            "major",
            "mechanical",
            ["ISO 29148:5.4.2.3", "INCOSE GtWR 2.2.4", "NASA TRC-M545"],
            "Imprecise adverbs/adjectives ('quickly', 'roughly', 'sufficiently') without quantitative scale.",
            "The system shall respond quickly to user inputs.",
            "The system shall respond to user inputs within 200 ms under nominal conditions.",
        ),
        # --- test plan defects -----------------------------------------------
        _e(
            DefectType.AMBIGUOUS_EXPECTED_RESULTS,
            "Ambiguous expected results",
            "test_plan",
            "major",
            "mechanical",
            ["ISO 29119-4:5.2.3.7", "ISO 29148:7.4.2", "DO-178C 6.4.2.2"],
            "Expected result is subjective ('appears correct', 'works', 'is responsive') instead of deterministic.",
            "Verify that the system displays the correct warning message.",
            "Verify that the system displays 'Battery low' within 2 s after the battery level drops below 15%.",
        ),
        _e(
            DefectType.FABRICATED_REQ_ID,
            "Fabricated requirement ID",
            "test_plan",
            "critical",
            "mechanical",
            ["ISO 29148:6.3.2.3", "ISO 29119-3:6.4.2", "DO-178C 6.4.1"],
            "Test case references a requirement ID that does not exist in the approved baseline.",
        ),
        _e(
            DefectType.COVERAGE_GAP,
            "Coverage gap",
            "test_plan",
            "critical",
            "domain_expert",
            ["ISO 29119-2:4.4.4", "ISO 29119-4", "DO-178C 6.4-6.5"],
            "A requirement or safety goal has no test cases that exercise its full logical conditions or boundaries.",
        ),
        _e(
            DefectType.INCORRECT_ACCEPTANCE_CRITERIA,
            "Incorrect acceptance criteria",
            "test_plan",
            "critical",
            "domain_expert",
            ["ISO 29119-4", "ISO 29148:6.4.2.4", "IEC 61508"],
            "Acceptance criteria contradict or fail to match the requirement they verify.",
        ),
        _e(
            DefectType.MISSING_ENTRY_EXIT_CRITERIA,
            "Missing entry/exit criteria",
            "test_plan",
            "critical",
            "mechanical",
            ["ISO 29119-3:7.2.7", "ISO 29148:8.2.4.2", "DO-178C 2.6.3"],
            "Test plan lacks measurable preconditions for starting tests or quantitative conditions for completing them.",
        ),
        _e(
            DefectType.MISSING_RISK_ANALYSIS,
            "Missing risk analysis",
            "test_plan",
            "major",
            "llm",
            ["ISO 29119-1:5.4.4", "ISO 26262-3:8.4", "DO-178C 2.4.7"],
            "Test plan does not identify hazards, failure modes, or risk-based prioritisation.",
        ),
        _e(
            DefectType.MISSING_TEARDOWN_CLEANUP,
            "Missing teardown/cleanup",
            "test_plan",
            "major",
            "mechanical",
            ["ISO 29119-3:5.5.2", "DO-178C 6.3.3", "ISO 26262-6:7.4.4.4"],
            "Test case alters state without specifying cleanup to restore the baseline environment.",
        ),
        _e(
            DefectType.REDUNDANT_COVERAGE,
            "Redundant coverage",
            "test_plan",
            "minor",
            "mechanical",
            ["ISO 29119-4:6.3.3", "DO-178C 6.4.4.2"],
            "Multiple test cases verify the same equivalence class without adding unique coverage.",
        ),
        _e(
            DefectType.SCHEMA_INCOMPLETE_FIELDS,
            "Schema incomplete fields",
            "test_plan",
            "major",
            "mechanical",
            ["ISO 29148:6.3.2.3", "ISO 29119-2:5.3.4"],
            "Mandatory test plan / test case fields are blank (objective, expected results, etc.).",
        ),
        _e(
            DefectType.SEVERITY_PRIORITY_CONFUSION,
            "Severity/priority confusion",
            "test_plan",
            "major",
            "domain_expert",
            ["ISO 29148:7.4.6", "ISO 29119-2:5.5.2", "ISO 26262-8 §10"],
            "Severity (technical impact) and priority (urgency) are conflated or swapped in defect classification.",
        ),
        _e(
            DefectType.UNRUNNABLE_PRECONDITIONS,
            "Unrunnable preconditions",
            "test_plan",
            "major",
            "domain_expert",
            ["ISO 29148:9.4.3.3", "ISO 29119-4:5.2.2", "DO-178C 6.4.4"],
            "Preconditions cannot be satisfied (impossible state, missing equipment, conflicting setup).",
        ),
        _e(
            DefectType.UNTRACEABLE_TEST_CASE,
            "Untraceable test case",
            "test_plan",
            "major",
            "mechanical",
            ["ISO 29148:7.5.3", "ISO 29119-4:5.4.5", "DO-178C 6.4.4"],
            "Test case is not linked to any approved requirement.",
        ),
    ]
)


class DefectInstance(BaseModel):
    """A concrete defect observed in a specific artefact."""

    id: str = Field(default_factory=lambda: f"def_{uuid4().hex[:10]}")
    defect_type: DefectType
    severity: Severity
    target_kind: TargetKind
    target_id: str
    evidence: str
    suggestion: str | None = None
    detector: Detector


class DefectReport(BaseModel):
    """Aggregated defect findings for one pipeline run."""

    plan_id: str | None = None
    defects: list[DefectInstance] = Field(default_factory=list)
    summary: dict[Severity, int] = Field(default_factory=dict)
    approved: bool = True

    def compute_summary(self) -> None:
        counts: dict[Severity, int] = {"critical": 0, "major": 0, "minor": 0}
        for d in self.defects:
            counts[d.severity] = counts.get(d.severity, 0) + 1
        self.summary = counts
        self.approved = counts["critical"] == 0


INDUSTRY_STANDARD_REFS: dict[Industry, list[str]] = {
    "generic": ["ISO/IEC/IEEE 29148", "ISO/IEC/IEEE 29119", "INCOSE GtWR"],
    "aerospace": ["DO-178C", "ARP4754A", "DO-254", "ISO/IEC/IEEE 29148"],
    "automotive": ["ISO 26262", "ASPICE", "ISO/SAE 21434", "ISO/IEC/IEEE 29148"],
    "medical": ["IEC 62304", "ISO 14971", "IEC 62366", "ISO 13485"],
    "energy": ["IEC 61508", "IEC 62443", "IEC 61850", "ISO/IEC/IEEE 29148"],
}

INDUSTRY_DEFECT_PRIORITIES: dict[Industry, list[DefectType]] = {
    "generic": [],
    "aerospace": [
        DefectType.TRACEABILITY_GAP,
        DefectType.UNTRACEABLE_TEST_CASE,
        DefectType.INCORRECT_ACCEPTANCE_CRITERIA,
        DefectType.MISSING_RISK_ANALYSIS,
    ],
    "automotive": [
        DefectType.MISSING_RISK_ANALYSIS,
        DefectType.INCORRECT_ACCEPTANCE_CRITERIA,
        DefectType.TRACEABILITY_GAP,
        DefectType.SEVERITY_PRIORITY_CONFUSION,
    ],
    "medical": [
        DefectType.MISSING_RISK_ANALYSIS,
        DefectType.UNRUNNABLE_PRECONDITIONS,
        DefectType.INCORRECT_ACCEPTANCE_CRITERIA,
        DefectType.TRACEABILITY_GAP,
    ],
    "energy": [
        DefectType.MISSING_RISK_ANALYSIS,
        DefectType.INCONSISTENCY_INTRA_DOC,
        DefectType.INCORRECT_ACCEPTANCE_CRITERIA,
        DefectType.TRACEABILITY_GAP,
    ],
}


def normalize_industry(industry: str | None) -> Industry:
    if industry in INDUSTRY_STANDARD_REFS:
        return industry  # type: ignore[return-value]
    return "generic"


def industry_standard_refs(industry: str | None) -> list[str]:
    return list(INDUSTRY_STANDARD_REFS[normalize_industry(industry)])


def prioritized_defect_types_for_industry(industry: str | None) -> list[DefectType]:
    return list(INDUSTRY_DEFECT_PRIORITIES[normalize_industry(industry)])


def defect_catalog_for_industry(industry: str | None) -> list[DefectCatalogEntry]:
    priorities = prioritized_defect_types_for_industry(industry)
    rank = {defect_type: idx for idx, defect_type in enumerate(priorities)}
    return sorted(
        CATALOG.values(),
        key=lambda entry: (rank.get(entry.id, len(rank)), entry.name),
    )


__all__ = [
    "CATALOG",
    "DefectCatalogEntry",
    "DefectCategory",
    "DefectInstance",
    "DefectReport",
    "DefectType",
    "DetectionDifficulty",
    "Detector",
    "Industry",
    "INDUSTRY_STANDARD_REFS",
    "defect_catalog_for_industry",
    "industry_standard_refs",
    "normalize_industry",
    "prioritized_defect_types_for_industry",
    "Severity",
    "TargetKind",
]
