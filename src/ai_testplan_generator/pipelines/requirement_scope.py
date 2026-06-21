"""Requirement selection rules shared by generation pipelines."""

from __future__ import annotations

from dataclasses import dataclass

from ai_testplan_generator.models import Requirement


@dataclass(frozen=True)
class RequirementScope:
    requirements: list[Requirement]
    needs_extraction: bool


def resolve_requirement_scope(
    *,
    requirements: list[Requirement],
    requirement_mode: str = "all",
    requirement_ids: list[str] | None = None,
) -> RequirementScope:
    """Return the requirements a run should use, or mark extraction required."""
    mode = requirement_mode or "all"
    ids = list(dict.fromkeys(requirement_ids or []))

    if mode == "reextract":
        return RequirementScope(requirements=[], needs_extraction=True)

    if mode == "selected":
        if not ids:
            raise RuntimeError("selected requirement mode requires at least one id")
        by_id = {req.id: req for req in requirements}
        missing = [req_id for req_id in ids if req_id not in by_id]
        if missing:
            raise RuntimeError(
                "selected requirements were not found in the project: " + ", ".join(missing[:10])
            )
        return RequirementScope(
            requirements=[by_id[req_id] for req_id in ids],
            needs_extraction=False,
        )

    if mode != "all":
        raise RuntimeError(f"unknown requirement mode: {mode}")

    return RequirementScope(
        requirements=requirements,
        needs_extraction=not requirements,
    )
