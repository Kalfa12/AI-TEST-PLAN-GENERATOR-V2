"""Minimal end-to-end demo of the autonomous pipeline.

Run:
    pip install -e .
    export OPENAI_API_KEY=...        # or ANTHROPIC_API_KEY / GOOGLE_API_KEY / ...
    export LLM_MODEL_SMART=gpt-5     # or any LiteLLM-compatible id
    python examples/run_autonomous.py path/to/spec.pdf path/to/norm.docx
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ai_testplan_generator import AutonomousPipeline, Brain
from ai_testplan_generator.models import DetailLevel


async def main(paths: list[Path]) -> None:
    brain = Brain.build()
    project_id = "demo_project"

    kb = brain.project_kb(project_id)
    for p in paths:
        res = await kb.ingest(p)
        print(
            f"[ingest] {p.name}: "
            f"{len(res.chunks)} chunks, {len(res.requirements)} requirements"
        )

    pipeline = AutonomousPipeline(brain)
    result = await pipeline.run(
        project_id=project_id,
        goal="Generate a full qualification test plan for the supplied specs.",
        detail_level=DetailLevel.DETAILED,
    )

    plan = result.plan
    print(f"\n== Plan: {plan.title if plan else '(none)'} ==")
    if plan:
        print(f"  scope:  {plan.scope}")
        print(f"  cases:  {len(plan.test_cases)}")
        print(f"  coverage entries: {len(plan.coverage_matrix)}")
    if result.schedule:
        print(f"  milestones: {len(result.schedule.milestones)}")
        print(f"  assignments: {len(result.schedule.assignments)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: run_autonomous.py <doc> [<doc> ...]", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main([Path(p) for p in sys.argv[1:]]))
