"""Defect aggregator - merges static + LLM + traceability findings.

Pure function node (no LLM). Builds the unified `DefectReport`:
 - runs `quality.static_checks` over requirements and the test plan
 - promotes typed `ReviewFinding`s from the TestPlan reviewer
 - promotes typed `ReviewFinding`s from the RequirementReviewer
 - lifts `TraceabilityReport` weak links / contradictions into defects

Writes `state.defect_report`.
"""

from __future__ import annotations

from ai_testplan_generator.agents.reviewer import ReviewReport
from ai_testplan_generator.agents.traceability import TraceabilityReport
from ai_testplan_generator.models import (
    DefectInstance,
    DefectReport,
    DefectType,
    Requirement,
    TestPlan,
)
from ai_testplan_generator.quality import check_requirements, check_test_plan


def _from_review(
    report: ReviewReport | None,
    fallback_target: str,
    detector: str,
) -> list[DefectInstance]:
    if report is None:
        return []
    out: list[DefectInstance] = []
    for f in report.findings:
        if f.defect_type is None:
            continue
        target_kind: str
        target_id: str
        if f.requirement_id:
            target_kind, target_id = "requirement", f.requirement_id
        elif f.test_case_id:
            target_kind, target_id = "test_case", f.test_case_id
        else:
            target_kind, target_id = "test_plan", fallback_target
        out.append(
            DefectInstance(
                defect_type=f.defect_type,
                severity=f.severity,
                target_kind=target_kind,  # type: ignore[arg-type]
                target_id=target_id,
                evidence=f.summary,
                suggestion=f.suggestion,
                detector=detector,  # type: ignore[arg-type]
            )
        )
    return out


def _from_trace(report: TraceabilityReport | None) -> list[DefectInstance]:
    if report is None:
        return []
    out: list[DefectInstance] = []
    for tc_id in report.weak_links:
        out.append(
            DefectInstance(
                defect_type=DefectType.UNTRACEABLE_TEST_CASE,
                severity="major",
                target_kind="test_case",
                target_id=tc_id,
                evidence="Traceability confidence below 0.5 — test does not clearly cover its claimed requirements.",
                suggestion="Tighten steps/acceptance to verify the claimed requirements, or remove the link.",
                detector="traceability",
            )
        )
    for c in report.contradictions:
        tc_id, _, note = c.partition(":")
        out.append(
            DefectInstance(
                defect_type=DefectType.INCONSISTENCY_INTRA_DOC,
                severity="critical",
                target_kind="test_case",
                target_id=tc_id.strip() or "unknown",
                evidence=note.strip() or "Step contradicts source chunk.",
                suggestion="Reconcile the test step with the source requirement.",
                detector="traceability",
            )
        )
    return out


_SEVERITY_RANK: dict[str, int] = {"critical": 3, "major": 2, "minor": 1}
# Detector preference when deduping — keep evidence from the more specific
# source. Static checks cite a line; reviewers cite a narrative.
_DETECTOR_RANK: dict[str, int] = {
    "static": 3,
    "traceability": 2,
    "reviewer": 1,
    "requirement_reviewer": 1,
}


def _dedup(defects: list[DefectInstance]) -> list[DefectInstance]:
    """Collapse defects that share (target_kind, target_id, defect_type).

    Three detectors can flag the same issue (e.g. a vague requirement is
    caught by the static lexicon, the requirement_reviewer, and shows up
    indirectly in the reviewer's findings). Keep the highest severity;
    break ties by detector preference.
    """
    best: dict[tuple[str, str, str], DefectInstance] = {}
    for d in defects:
        key = (d.target_kind, d.target_id, d.defect_type.value)
        current = best.get(key)
        if current is None:
            best[key] = d
            continue
        # Prefer higher severity. Ties go to the more specific detector.
        if _SEVERITY_RANK[d.severity] > _SEVERITY_RANK[current.severity]:
            best[key] = d
        elif _SEVERITY_RANK[d.severity] == _SEVERITY_RANK[current.severity]:
            if _DETECTOR_RANK.get(d.detector, 0) > _DETECTOR_RANK.get(
                current.detector, 0
            ):
                best[key] = d
    return list(best.values())


def build_defect_report(
    *,
    plan: TestPlan | None,
    requirements: list[Requirement],
    review_report: ReviewReport | None,
    requirement_review_report: ReviewReport | None,
    trace_report: TraceabilityReport | None,
) -> DefectReport:
    defects: list[DefectInstance] = []
    defects.extend(check_requirements(requirements))
    if plan is not None:
        defects.extend(check_test_plan(plan, requirements))
    defects.extend(
        _from_review(
            requirement_review_report,
            fallback_target=plan.id if plan else "plan",
            detector="requirement_reviewer",
        )
    )
    defects.extend(
        _from_review(
            review_report,
            fallback_target=plan.id if plan else "plan",
            detector="reviewer",
        )
    )
    defects.extend(_from_trace(trace_report))

    defects = _dedup(defects)

    report = DefectReport(plan_id=plan.id if plan else None, defects=defects)
    report.compute_summary()
    _record_metrics(report)
    return report


def _record_metrics(report: DefectReport) -> None:
    try:
        from ai_testplan_generator.telemetry.metrics import defects_total
    except Exception:
        return
    try:
        counter = defects_total()
    except RuntimeError:
        return  # metrics not initialised (e.g. in unit-test contexts)
    for d in report.defects:
        counter.labels(
            defect_type=d.defect_type.value,
            severity=d.severity,
            detector=d.detector,
        ).inc()
