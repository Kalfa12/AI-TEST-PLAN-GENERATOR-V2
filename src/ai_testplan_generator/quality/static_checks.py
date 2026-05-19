"""Mechanically-detectable defect checks for requirements and test plans.

Each detector is a small pure function over the domain objects. Detectors
emit `DefectInstance` with `detector="static"`. No LLM, no IO.

Severity defaults come from the catalog but a detector may override per
instance (e.g. a missing acceptance criterion is more severe on a safety
requirement). Keep wordlists / regexes inline — the taxonomy lives in
[models/defects.py](../models/defects.py); this file is just the rules.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ai_testplan_generator.models import (
    CATALOG,
    DefectInstance,
    DefectType,
    Requirement,
    TestCase,
    TestPlan,
)
from ai_testplan_generator.models.defects import Severity


def _severity(defect: DefectType, override: Severity | None = None) -> Severity:
    return override or CATALOG[defect].default_severity


def _mk(
    defect: DefectType,
    target_kind: str,
    target_id: str,
    evidence: str,
    suggestion: str | None = None,
    severity_override: Severity | None = None,
) -> DefectInstance:
    return DefectInstance(
        defect_type=defect,
        severity=_severity(defect, severity_override),
        target_kind=target_kind,  # type: ignore[arg-type]
        target_id=target_id,
        evidence=evidence,
        suggestion=suggestion,
        detector="static",
    )


# ---------------------------------------------------------------------------
# Lexicons / regexes
# ---------------------------------------------------------------------------

_TBD_RE = re.compile(r"\b(TBD|TBR|TBS|TBC|TBA)\b")
_NON_SHALL_MODALS = re.compile(r"\b(should|may|will|must)\b", re.IGNORECASE)
_SHALL_RE = re.compile(r"\bshall\b", re.IGNORECASE)
_UNIVERSAL_RE = re.compile(
    r"\b(always|never|all|every|every\s+single|100\s*%)\b", re.IGNORECASE
)
_UNBOUNDED_RE = re.compile(
    r"(\betc\.?|including but not limited to|and so on|and so forth|"
    r"\bsuch as\b[^.]*\.)",
    re.IGNORECASE,
)
_VAGUE_RE = re.compile(
    r"\b(quickly|fast|approximately|roughly|usually|often|significantly|"
    r"sufficiently|adequate|adequately|appropriate|appropriately|robust|"
    r"seamless|user[- ]friendly|reasonable|reasonably|effective|efficiently|"
    r"as needed|as required|if necessary)\b",
    re.IGNORECASE,
)
_SUBJECTIVE_RE = re.compile(
    r"\b(pleasant|pleasing|attractive|good|nice|intuitive|elegant|beautiful)\b",
    re.IGNORECASE,
)
_PRONOUN_LEAD_RE = re.compile(
    r"^\s*(it|they|this|that|these|those)\b", re.IGNORECASE
)
_COMPOUND_HINTS_RE = re.compile(
    r"(\band\s+shall\b|;\s*shall\b|,\s*and\s+(?:then\s+)?shall\b)",
    re.IGNORECASE,
)
_STATE_CHANGE_RE = re.compile(
    r"\b(create|insert|write|configure|upload|populate|provision|enable|set\s+up)\b",
    re.IGNORECASE,
)
_CLEANUP_RE = re.compile(
    r"\b(teardown|tear[- ]down|cleanup|clean[- ]up|delete|remove|restore|revert|"
    r"reset|disable|deprovision)\b",
    re.IGNORECASE,
)
_VAGUE_RESULT_RE = re.compile(
    r"\b(works|functions normally|appears|looks correct|behaves correctly|"
    r"is responsive|is acceptable|is fine|ok)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Requirement-level detectors
# ---------------------------------------------------------------------------


def _check_tbd(req: Requirement) -> list[DefectInstance]:
    m = _TBD_RE.search(req.statement)
    if not m:
        return []
    return [
        _mk(
            DefectType.TBD_PLACEHOLDER,
            "requirement",
            req.id,
            f"Statement contains unresolved placeholder '{m.group(0)}'.",
            "Replace with a concrete value before baselining.",
        )
    ]


def _check_modality(req: Requirement) -> list[DefectInstance]:
    if _SHALL_RE.search(req.statement):
        return []
    m = _NON_SHALL_MODALS.search(req.statement)
    if not m:
        return []
    return [
        _mk(
            DefectType.MODALITY_DRIFT,
            "requirement",
            req.id,
            f"Uses '{m.group(0)}' as primary modal verb; no 'shall' present.",
            "Use 'shall' for binding obligations; reserve 'should/may' for recommendations.",
        )
    ]


def _check_universal_qualifier(req: Requirement) -> list[DefectInstance]:
    m = _UNIVERSAL_RE.search(req.statement)
    if not m:
        return []
    return [
        _mk(
            DefectType.UNIVERSAL_QUALIFIER_MISUSE,
            "requirement",
            req.id,
            f"Uses absolute quantifier '{m.group(0)}' without bounded scope.",
            "Quantify the condition (rate, MTBF, coverage threshold) so it is verifiable.",
        )
    ]


def _check_unbounded_enum(req: Requirement) -> list[DefectInstance]:
    m = _UNBOUNDED_RE.search(req.statement)
    if not m:
        return []
    return [
        _mk(
            DefectType.UNBOUNDED_ENUMERATION,
            "requirement",
            req.id,
            f"Open-ended enumeration: '{m.group(0).strip()}'.",
            "Replace with a closed list of items.",
        )
    ]


def _check_vague_modifiers(req: Requirement) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    if (m := _VAGUE_RE.search(req.statement)) is not None:
        out.append(
            _mk(
                DefectType.VAGUE_MODIFIERS,
                "requirement",
                req.id,
                f"Vague modifier '{m.group(0)}' lacks quantitative bound.",
                "Quantify with units and tolerances (e.g. '< 200 ms', '+/- 2%').",
            )
        )
    if (m := _SUBJECTIVE_RE.search(req.statement)) is not None:
        out.append(
            _mk(
                DefectType.SUBJECTIVE_WORDING,
                "requirement",
                req.id,
                f"Subjective term '{m.group(0)}' has no objective verification criterion.",
                "Replace with a measurable property (e.g. specific dB, click count, completion time).",
            )
        )
    return out


def _check_compound(req: Requirement) -> list[DefectInstance]:
    if _SHALL_RE.findall(req.statement).__len__() >= 2:
        return [
            _mk(
                DefectType.COMPOUND_REQUIREMENT,
                "requirement",
                req.id,
                "Statement contains multiple 'shall' clauses.",
                "Split into one requirement per obligation.",
            )
        ]
    if _COMPOUND_HINTS_RE.search(req.statement):
        return [
            _mk(
                DefectType.COMPOUND_REQUIREMENT,
                "requirement",
                req.id,
                "Statement joins multiple obligations with 'and shall' / ';'.",
                "Split into one requirement per obligation.",
            )
        ]
    return []


def _check_pronoun(req: Requirement) -> list[DefectInstance]:
    sentences = [s for s in re.split(r"[.!?]\s+", req.statement) if s.strip()]
    if len(sentences) < 2:
        return []
    if _PRONOUN_LEAD_RE.match(sentences[1]):
        return [
            _mk(
                DefectType.PRONOUN_REFERENCE,
                "requirement",
                req.id,
                "Subsequent sentence begins with an ambiguous pronoun (it/they/this/that).",
                "Replace the pronoun with the explicit antecedent noun.",
            )
        ]
    return []


def _check_missing_rationale(req: Requirement) -> list[DefectInstance]:
    if req.rationale:
        return []
    return [
        _mk(
            DefectType.MISSING_RATIONALE,
            "requirement",
            req.id,
            "Requirement has no rationale.",
            "Add a one-line justification (the 'why') to support impact analysis.",
        )
    ]


def _check_missing_acceptance_hint(req: Requirement) -> list[DefectInstance]:
    if req.acceptance_hint or _has_numeric_bound(req.statement):
        return []
    severity: Severity = "critical" if req.priority >= 4 else "major"
    return [
        _mk(
            DefectType.MISSING_ACCEPTANCE_CRITERIA,
            "requirement",
            req.id,
            "No acceptance hint and no numeric/measurable bound in the statement.",
            "Add a measurable threshold or pass/fail criterion.",
            severity_override=severity,
        )
    ]


def _has_numeric_bound(text: str) -> bool:
    return bool(re.search(r"\d+(\.\d+)?\s*(%|ms|s|min|h|hz|khz|mhz|"
                          r"kg|g|mb|gb|kb|bps|kbps|mbps|gbps|"
                          r"°c|°f|deg|c|f|v|w|a|n|nm|mm|cm|m|km|"
                          r"records?|requests?|attempts?|users?)\b",
                          text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Test-plan-level detectors
# ---------------------------------------------------------------------------


def _check_fabricated_ids(plan: TestPlan, known: set[str]) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    for tc in plan.test_cases:
        for rid in tc.requirement_ids:
            if rid not in known:
                out.append(
                    _mk(
                        DefectType.FABRICATED_REQ_ID,
                        "test_case",
                        tc.id,
                        f"References requirement '{rid}' not present in the approved baseline.",
                        "Remove the link or fix the requirement ID.",
                    )
                )
    return out


def _check_untraceable_tcs(plan: TestPlan) -> list[DefectInstance]:
    return [
        _mk(
            DefectType.UNTRACEABLE_TEST_CASE,
            "test_case",
            tc.id,
            "Test case has no requirement_ids.",
            "Link this test case to at least one approved requirement.",
        )
        for tc in plan.test_cases
        if not tc.requirement_ids
    ]


def _check_dead_requirements(
    reqs: list[Requirement], plan: TestPlan
) -> list[DefectInstance]:
    covered: set[str] = set()
    for tc in plan.test_cases:
        covered.update(tc.requirement_ids)
    covered.update(plan.coverage_matrix.keys())
    return [
        _mk(
            DefectType.DEAD_REQUIREMENT,
            "requirement",
            r.id,
            "Requirement is not covered by any test case or coverage matrix entry.",
            "Either cover it with a test case or remove it.",
        )
        for r in reqs
        if r.id not in covered
    ]


def _check_traceability_gap(reqs: list[Requirement], plan: TestPlan) -> list[DefectInstance]:
    matrix_ids = set(plan.coverage_matrix.keys())
    out: list[DefectInstance] = []
    for r in reqs:
        if not r.source_chunk_ids and not r.source_document_id:
            out.append(
                _mk(
                    DefectType.TRACEABILITY_GAP,
                    "requirement",
                    r.id,
                    "Requirement has no upward link to a source document/chunk.",
                    "Trace back to the originating spec section.",
                )
            )
        if r.id not in matrix_ids and not any(
            r.id in tc.requirement_ids for tc in plan.test_cases
        ):
            # Avoid double-firing with DEAD_REQUIREMENT — that detector handles this.
            continue
    return out


def _check_schema_incomplete(plan: TestPlan) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    for tc in plan.test_cases:
        missing: list[str] = []
        if not tc.objective.strip():
            missing.append("objective")
        for step in tc.steps:
            if not step.expected_result.strip():
                missing.append(f"steps[{step.index}].expected_result")
        if missing:
            out.append(
                _mk(
                    DefectType.SCHEMA_INCOMPLETE_FIELDS,
                    "test_case",
                    tc.id,
                    f"Missing required fields: {', '.join(missing)}.",
                    "Populate every mandatory field before exporting the plan.",
                )
            )
    return out


def _check_missing_acceptance_on_tcs(plan: TestPlan) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    for tc in plan.test_cases:
        if not tc.acceptance_criteria:
            out.append(
                _mk(
                    DefectType.MISSING_ACCEPTANCE_CRITERIA,
                    "test_case",
                    tc.id,
                    "Test case has no acceptance criteria.",
                    "Add at least one measurable pass/fail criterion.",
                )
            )
            continue
        has_measurable = any(
            c.measurable and c.tolerance for c in tc.acceptance_criteria
        )
        if not has_measurable:
            out.append(
                _mk(
                    DefectType.MISSING_ACCEPTANCE_CRITERIA,
                    "test_case",
                    tc.id,
                    "No measurable acceptance criterion with a defined tolerance.",
                    "Add a tolerance/threshold (e.g. '< 200 ms', '+/- 2% FS').",
                )
            )
    return out


def _check_entry_exit(plan: TestPlan) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    if not plan.entry_criteria:
        out.append(
            _mk(
                DefectType.MISSING_ENTRY_EXIT_CRITERIA,
                "test_plan",
                plan.id,
                "Plan has no entry criteria.",
                "Define preconditions that must be met before testing begins.",
            )
        )
    if not plan.exit_criteria:
        out.append(
            _mk(
                DefectType.MISSING_ENTRY_EXIT_CRITERIA,
                "test_plan",
                plan.id,
                "Plan has no exit criteria.",
                "Define measurable conditions for declaring testing complete (coverage %, open defects).",
            )
        )
    return out


def _check_redundant_coverage(plan: TestPlan) -> list[DefectInstance]:
    """Flag pairs of TCs that cover the same reqs with the same testing_types
    and ≥80% objective-token overlap. Cheap shingle compare."""

    out: list[DefectInstance] = []
    seen: list[tuple[frozenset[str], frozenset[str], frozenset[str], str]] = []
    for tc in plan.test_cases:
        if not tc.requirement_ids:
            continue
        sig_reqs = frozenset(tc.requirement_ids)
        sig_types = frozenset(t.lower() for t in tc.testing_types)
        toks = frozenset(re.findall(r"\w{4,}", tc.objective.lower()))
        for prev_reqs, prev_types, prev_toks, prev_id in seen:
            if prev_reqs != sig_reqs or prev_types != sig_types:
                continue
            if not toks or not prev_toks:
                continue
            overlap = len(toks & prev_toks) / max(len(toks | prev_toks), 1)
            if overlap >= 0.8:
                out.append(
                    _mk(
                        DefectType.REDUNDANT_COVERAGE,
                        "test_case",
                        tc.id,
                        f"Duplicates {prev_id}: same requirement_ids, same testing_types, ≥80% objective overlap.",
                        "Merge with the duplicate or differentiate input boundaries.",
                    )
                )
                break
        seen.append((sig_reqs, sig_types, toks, tc.id))
    return out


def _check_teardown(plan: TestPlan) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    for tc in plan.test_cases:
        steps_text = " ".join(s.action for s in tc.steps)
        if not _STATE_CHANGE_RE.search(steps_text):
            continue
        teardown_text = (tc.teardown or "") + " " + steps_text
        if _CLEANUP_RE.search(teardown_text):
            continue
        out.append(
            _mk(
                DefectType.MISSING_TEARDOWN_CLEANUP,
                "test_case",
                tc.id,
                "Test mutates state (create/insert/configure/...) without a cleanup step or teardown.",
                "Add a teardown that restores the baseline environment.",
            )
        )
    return out


def _check_ambiguous_results(plan: TestPlan) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    for tc in plan.test_cases:
        for step in tc.steps:
            m = _VAGUE_RESULT_RE.search(step.expected_result)
            if m:
                out.append(
                    _mk(
                        DefectType.AMBIGUOUS_EXPECTED_RESULTS,
                        "test_case",
                        tc.id,
                        f"Step {step.index} expected result is subjective ('{m.group(0)}').",
                        "State a deterministic, measurable outcome.",
                    )
                )
                break
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_requirements(reqs: Iterable[Requirement]) -> list[DefectInstance]:
    out: list[DefectInstance] = []
    for r in reqs:
        out.extend(_check_tbd(r))
        out.extend(_check_modality(r))
        out.extend(_check_universal_qualifier(r))
        out.extend(_check_unbounded_enum(r))
        out.extend(_check_vague_modifiers(r))
        out.extend(_check_compound(r))
        out.extend(_check_pronoun(r))
        out.extend(_check_missing_rationale(r))
        out.extend(_check_missing_acceptance_hint(r))
    return out


def check_test_plan(
    plan: TestPlan,
    requirements: list[Requirement],
) -> list[DefectInstance]:
    known = {r.id for r in requirements}
    out: list[DefectInstance] = []
    out.extend(_check_fabricated_ids(plan, known))
    out.extend(_check_untraceable_tcs(plan))
    out.extend(_check_dead_requirements(requirements, plan))
    out.extend(_check_traceability_gap(requirements, plan))
    out.extend(_check_schema_incomplete(plan))
    out.extend(_check_missing_acceptance_on_tcs(plan))
    out.extend(_check_entry_exit(plan))
    out.extend(_check_redundant_coverage(plan))
    out.extend(_check_teardown(plan))
    out.extend(_check_ambiguous_results(plan))
    # TBD scan over plan text fields
    plan_text_blob = " ".join(
        [
            plan.title,
            plan.scope or "",
            plan.strategy or "",
            plan.introduction or "",
            *plan.objectives,
            *plan.entry_criteria,
            *plan.exit_criteria,
            *plan.risks,
        ]
    )
    if (m := _TBD_RE.search(plan_text_blob)) is not None:
        out.append(
            _mk(
                DefectType.TBD_PLACEHOLDER,
                "test_plan",
                plan.id,
                f"Plan body contains placeholder '{m.group(0)}'.",
                "Resolve the placeholder before exporting.",
            )
        )
    return out
