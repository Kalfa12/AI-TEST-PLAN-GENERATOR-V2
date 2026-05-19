"""Unit tests for the mechanical defect detectors.

One positive + one negative case per detector. Plus a catalog shape
snapshot test (every entry valid, no duplicates).
"""

from __future__ import annotations

from ai_testplan_generator.models import (
    CATALOG,
    AcceptanceCriterion,
    DefectType,
    Requirement,
    RequirementKind,
    TestCase,
    TestPlan,
    TestStep,
)
from ai_testplan_generator.quality.static_checks import (
    check_requirements,
    check_test_plan,
)


def _req(
    statement: str,
    *,
    rationale: str | None = "because reasons",
    acceptance_hint: str | None = "within tolerance",
    priority: int = 3,
    kind: RequirementKind = RequirementKind.FUNCTIONAL,
) -> Requirement:
    return Requirement(
        kind=kind,
        title="test req",
        statement=statement,
        rationale=rationale,
        acceptance_hint=acceptance_hint,
        priority=priority,
        source_document_id="doc1",
    )


def _types(reqs_or_plan: list) -> set[DefectType]:
    return {d.defect_type for d in reqs_or_plan}


# --- catalog -----------------------------------------------------------------


def test_catalog_shape() -> None:
    assert len(CATALOG) == len(DefectType), "every enum value must have a catalog entry"
    assert len({e.id for e in CATALOG.values()}) == len(CATALOG), "no duplicate ids"
    for entry in CATALOG.values():
        assert entry.standard_refs, f"{entry.id} missing standard refs"
        assert entry.description.strip(), f"{entry.id} missing description"
        assert entry.detection_difficulty in {"mechanical", "llm", "domain_expert"}
        assert entry.default_severity in {"critical", "major", "minor"}
        assert entry.category in {"requirement", "test_plan"}


# --- requirement detectors ---------------------------------------------------


def test_tbd_placeholder_positive() -> None:
    reqs = [_req("The system shall respond within TBD seconds.")]
    assert DefectType.TBD_PLACEHOLDER in _types(check_requirements(reqs))


def test_tbd_placeholder_negative() -> None:
    reqs = [_req("The system shall respond within 200 ms.")]
    assert DefectType.TBD_PLACEHOLDER not in _types(check_requirements(reqs))


def test_modality_drift_positive() -> None:
    reqs = [_req("The system should log errors to the console.")]
    assert DefectType.MODALITY_DRIFT in _types(check_requirements(reqs))


def test_modality_drift_negative() -> None:
    reqs = [_req("The system shall log errors to the console.")]
    assert DefectType.MODALITY_DRIFT not in _types(check_requirements(reqs))


def test_universal_qualifier_positive() -> None:
    reqs = [_req("The system shall never crash under any load.")]
    assert DefectType.UNIVERSAL_QUALIFIER_MISUSE in _types(check_requirements(reqs))


def test_universal_qualifier_negative() -> None:
    reqs = [_req("The system shall achieve an MTBF of 10000 h.")]
    assert DefectType.UNIVERSAL_QUALIFIER_MISUSE not in _types(check_requirements(reqs))


def test_unbounded_enum_positive() -> None:
    reqs = [_req("The system shall support formats PDF, XML, etc.")]
    assert DefectType.UNBOUNDED_ENUMERATION in _types(check_requirements(reqs))


def test_unbounded_enum_negative() -> None:
    reqs = [_req("The system shall support formats PDF v1.4 and XML v1.0.")]
    assert DefectType.UNBOUNDED_ENUMERATION not in _types(check_requirements(reqs))


def test_vague_modifiers_positive() -> None:
    reqs = [_req("The system shall respond quickly to user inputs.")]
    assert DefectType.VAGUE_MODIFIERS in _types(check_requirements(reqs))


def test_vague_modifiers_negative() -> None:
    reqs = [_req("The system shall respond to user inputs within 200 ms.")]
    assert DefectType.VAGUE_MODIFIERS not in _types(check_requirements(reqs))


def test_subjective_wording_positive() -> None:
    reqs = [_req("The system shall provide a pleasant interface.")]
    assert DefectType.SUBJECTIVE_WORDING in _types(check_requirements(reqs))


def test_subjective_wording_negative() -> None:
    reqs = [_req("The system shall complete startup within 5 s.")]
    assert DefectType.SUBJECTIVE_WORDING not in _types(check_requirements(reqs))


def test_compound_positive() -> None:
    reqs = [
        _req("The system shall calculate the trajectory and shall transmit it to ground control.")
    ]
    assert DefectType.COMPOUND_REQUIREMENT in _types(check_requirements(reqs))


def test_compound_negative() -> None:
    reqs = [_req("The system shall transmit the computed trajectory to ground control.")]
    assert DefectType.COMPOUND_REQUIREMENT not in _types(check_requirements(reqs))


def test_pronoun_positive() -> None:
    reqs = [
        _req(
            "The control unit sends data to the display. "
            "It then enters sleep mode at 30 mW."
        )
    ]
    assert DefectType.PRONOUN_REFERENCE in _types(check_requirements(reqs))


def test_pronoun_negative() -> None:
    reqs = [
        _req(
            "The control unit sends data to the display. "
            "The control unit then enters sleep mode at 30 mW."
        )
    ]
    assert DefectType.PRONOUN_REFERENCE not in _types(check_requirements(reqs))


def test_missing_rationale_positive() -> None:
    reqs = [_req("The system shall support 1000 concurrent users.", rationale=None)]
    assert DefectType.MISSING_RATIONALE in _types(check_requirements(reqs))


def test_missing_rationale_negative() -> None:
    reqs = [
        _req(
            "The system shall support 1000 concurrent users.",
            rationale="Matches the SLA committed to enterprise customers.",
        )
    ]
    assert DefectType.MISSING_RATIONALE not in _types(check_requirements(reqs))


def test_missing_acceptance_positive() -> None:
    reqs = [
        _req(
            "The system shall provide secure user access.",
            acceptance_hint=None,
        )
    ]
    assert DefectType.MISSING_ACCEPTANCE_CRITERIA in _types(check_requirements(reqs))


def test_missing_acceptance_negative_via_numeric_bound() -> None:
    reqs = [
        _req(
            "The system shall complete authentication within 500 ms.",
            acceptance_hint=None,
        )
    ]
    assert DefectType.MISSING_ACCEPTANCE_CRITERIA not in _types(check_requirements(reqs))


# --- test-plan detectors -----------------------------------------------------


def _step(idx: int, action: str = "do thing", expected: str = "value is 1 +/- 0.1") -> TestStep:
    return TestStep(index=idx, action=action, expected_result=expected)


_UNSET: object = object()


def _tc(
    *,
    id_: str = "tc_1",
    req_ids: list[str] | None = None,
    title: str = "TC",
    objective: str = "verify response time bound",
    steps: list[TestStep] | None = None,
    acceptance: list[AcceptanceCriterion] | object = _UNSET,
    testing_types: list[str] | None = None,
    teardown: str | None = "Restore database to baseline state.",
) -> TestCase:
    default_ac = [
        AcceptanceCriterion(statement="latency < 200 ms", measurable=True, tolerance="< 200 ms")
    ]
    return TestCase(
        id=id_,
        title=title,
        objective=objective,
        testing_types=testing_types or ["functional"],
        steps=steps or [_step(1)],
        acceptance_criteria=default_ac if acceptance is _UNSET else acceptance,  # type: ignore[arg-type]
        requirement_ids=req_ids if req_ids is not None else ["req1"],
        teardown=teardown,
    )


def _plan(test_cases: list[TestCase], **kw) -> TestPlan:
    defaults = dict(
        title="Plan",
        scope="in-scope items",
        strategy="risk-based",
        entry_criteria=["env ready"],
        exit_criteria=["100% planned tests executed"],
        test_cases=test_cases,
    )
    defaults.update(kw)
    return TestPlan(**defaults)


def test_fabricated_req_id_positive() -> None:
    reqs = [_req("The system shall do X within 1 s.")]
    known = [reqs[0]]
    real_id = known[0].id
    tc = _tc(req_ids=[real_id, "req_does_not_exist"])
    plan = _plan([tc])
    types = _types(check_test_plan(plan, known))
    assert DefectType.FABRICATED_REQ_ID in types


def test_fabricated_req_id_negative() -> None:
    reqs = [_req("The system shall do X within 1 s.")]
    tc = _tc(req_ids=[reqs[0].id])
    plan = _plan([tc])
    assert DefectType.FABRICATED_REQ_ID not in _types(check_test_plan(plan, reqs))


def test_untraceable_test_case_positive() -> None:
    plan = _plan([_tc(req_ids=[])])
    assert DefectType.UNTRACEABLE_TEST_CASE in _types(check_test_plan(plan, []))


def test_untraceable_test_case_negative() -> None:
    reqs = [_req("The system shall do X within 1 s.")]
    plan = _plan([_tc(req_ids=[reqs[0].id])])
    assert DefectType.UNTRACEABLE_TEST_CASE not in _types(check_test_plan(plan, reqs))


def test_dead_requirement_positive() -> None:
    reqs = [_req("The system shall do X within 1 s."), _req("The system shall do Y within 2 s.")]
    plan = _plan([_tc(req_ids=[reqs[0].id])])
    assert DefectType.DEAD_REQUIREMENT in _types(check_test_plan(plan, reqs))


def test_dead_requirement_negative() -> None:
    reqs = [_req("The system shall do X within 1 s.")]
    plan = _plan([_tc(req_ids=[reqs[0].id])])
    assert DefectType.DEAD_REQUIREMENT not in _types(check_test_plan(plan, reqs))


def test_schema_incomplete_positive() -> None:
    tc = _tc(steps=[_step(1, expected="")])
    plan = _plan([tc])
    assert DefectType.SCHEMA_INCOMPLETE_FIELDS in _types(check_test_plan(plan, []))


def test_schema_incomplete_negative() -> None:
    plan = _plan([_tc()])
    assert DefectType.SCHEMA_INCOMPLETE_FIELDS not in _types(check_test_plan(plan, []))


def test_missing_acceptance_on_tc_positive() -> None:
    reqs = [_req("The system shall do X in 1 s.")]
    plan = _plan([_tc(req_ids=[reqs[0].id], acceptance=[])])
    assert DefectType.MISSING_ACCEPTANCE_CRITERIA in _types(check_test_plan(plan, reqs))


def test_missing_acceptance_on_tc_negative() -> None:
    reqs = [_req("The system shall do X in 1 s.")]
    plan = _plan([_tc(req_ids=[reqs[0].id])])
    assert DefectType.MISSING_ACCEPTANCE_CRITERIA not in _types(check_test_plan(plan, reqs))


def test_missing_entry_exit_positive() -> None:
    reqs = [_req("The system shall do X in 1 s.")]
    plan = _plan(
        [_tc(req_ids=[reqs[0].id])], entry_criteria=[], exit_criteria=[]
    )
    assert DefectType.MISSING_ENTRY_EXIT_CRITERIA in _types(check_test_plan(plan, reqs))


def test_missing_entry_exit_negative() -> None:
    reqs = [_req("The system shall do X in 1 s.")]
    plan = _plan([_tc(req_ids=[reqs[0].id])])
    assert DefectType.MISSING_ENTRY_EXIT_CRITERIA not in _types(check_test_plan(plan, reqs))


def test_redundant_coverage_positive() -> None:
    reqs = [_req("The system shall respond in under 1 s.")]
    rid = reqs[0].id
    tc1 = _tc(id_="tc1", req_ids=[rid], objective="verify response latency bound is satisfied at peak")
    tc2 = _tc(id_="tc2", req_ids=[rid], objective="verify response latency bound is satisfied at peak")
    plan = _plan([tc1, tc2])
    assert DefectType.REDUNDANT_COVERAGE in _types(check_test_plan(plan, reqs))


def test_redundant_coverage_negative() -> None:
    reqs = [_req("The system shall respond in under 1 s.")]
    rid = reqs[0].id
    tc1 = _tc(id_="tc1", req_ids=[rid], objective="verify nominal latency at baseline load")
    tc2 = _tc(id_="tc2", req_ids=[rid], objective="verify boundary latency at saturation load")
    plan = _plan([tc1, tc2])
    assert DefectType.REDUNDANT_COVERAGE not in _types(check_test_plan(plan, reqs))


def test_missing_teardown_positive() -> None:
    tc = _tc(
        steps=[_step(1, action="Create a test user in the database", expected="user exists")],
        teardown=None,
    )
    plan = _plan([tc])
    assert DefectType.MISSING_TEARDOWN_CLEANUP in _types(check_test_plan(plan, []))


def test_missing_teardown_negative() -> None:
    tc = _tc(
        steps=[_step(1, action="Create a test user in the database", expected="user exists")],
        teardown="Delete the test user and reset the user table.",
    )
    plan = _plan([tc])
    assert DefectType.MISSING_TEARDOWN_CLEANUP not in _types(check_test_plan(plan, []))


def test_ambiguous_expected_results_positive() -> None:
    tc = _tc(steps=[_step(1, expected="The system works")])
    plan = _plan([tc])
    assert DefectType.AMBIGUOUS_EXPECTED_RESULTS in _types(check_test_plan(plan, []))


def test_ambiguous_expected_results_negative() -> None:
    plan = _plan([_tc()])
    assert DefectType.AMBIGUOUS_EXPECTED_RESULTS not in _types(check_test_plan(plan, []))


def test_tbd_in_plan_body_positive() -> None:
    plan = _plan([_tc()], strategy="To be defined: TBD")
    assert DefectType.TBD_PLACEHOLDER in _types(check_test_plan(plan, []))
