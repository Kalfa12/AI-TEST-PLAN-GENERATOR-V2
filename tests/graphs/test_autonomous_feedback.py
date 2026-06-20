from __future__ import annotations

from ai_testplan_generator.agents.reviewer import ReviewFinding, ReviewReport
from ai_testplan_generator.agents.traceability import TraceabilityReport
from ai_testplan_generator.graphs.autonomous import AutonomousState, _generator_feedback
from ai_testplan_generator.models import DetailLevel
from ai_testplan_generator.models.defects import DefectInstance, DefectReport, DefectType


def test_generator_feedback_combines_review_traceability_and_defect_findings() -> None:
    state = AutonomousState(
        session_id="session-a",
        project_id="project-a",
        goal="Generate trusted tests",
        detail_level=DetailLevel.DETAILED,
        review_report=ReviewReport(
            approved=False,
            findings=[
                ReviewFinding(
                    test_case_id="tc_1",
                    severity="major",
                    summary="Expected result is vague.",
                    suggestion="Make the expected result measurable.",
                )
            ],
        ),
        trace_report=TraceabilityReport(
            plan_id="plan-a",
            weak_links=["tc_2"],
            contradictions=["tc_3: requirement says enabled, test expects disabled"],
        ),
        defect_report=DefectReport(
            plan_id="plan-a",
            approved=False,
            defects=[
                DefectInstance(
                    defect_type=DefectType.UNTRACEABLE_TEST_CASE,
                    severity="major",
                    target_kind="test_case",
                    target_id="tc_4",
                    evidence="No source chunk supports this test case.",
                    suggestion="Link it to source evidence.",
                    detector="traceability",
                )
            ],
        ),
        user_feedback={"generator": ["User asked for fewer implementation details."]},
    )

    feedback = _generator_feedback(state)

    assert any("Reviewer major finding on tc_1" in item for item in feedback)
    assert any("Traceability weak link: revise test case tc_2" in item for item in feedback)
    assert any("Traceability contradiction: tc_3" in item for item in feedback)
    assert any("Defect major on test_case tc_4" in item for item in feedback)
    assert "User asked for fewer implementation details." in feedback
