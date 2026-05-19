"""Quality / defect-detection layer.

Pure-Python detectors that emit `DefectInstance`s over Requirements and
TestPlans. No LLM calls live here — these are the "mechanically
detectable" tier of the taxonomy (regex, wordlists, structural checks).
LLM-tier checks live on the reviewer agents.
"""

from ai_testplan_generator.quality.static_checks import (
    check_requirements,
    check_test_plan,
)

__all__ = ["check_requirements", "check_test_plan"]
