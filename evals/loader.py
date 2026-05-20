"""Load a benchmark folder into typed objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from ai_testplan_generator.models import Requirement, RequirementKind

from evals.scoring import ExpectedDefect, ExpectedRequirement


@dataclass
class Benchmark:
    name: str
    description: str
    path: Path
    spec_path: Path
    expected_requirements: list[ExpectedRequirement]
    expected_defects: list[ExpectedDefect]
    prefab_requirements_path: Path | None


def load_benchmark(folder: Path) -> Benchmark:
    folder = folder.resolve()
    expected_yaml = folder / "expected.yaml"
    if not expected_yaml.exists():
        raise FileNotFoundError(f"Benchmark missing expected.yaml: {folder}")

    with expected_yaml.open() as f:
        data = yaml.safe_load(f)

    spec_path = folder / data["spec"]
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    prefab = folder / "prefab_requirements.json"
    return Benchmark(
        name=data.get("name", folder.name),
        description=data.get("description", ""),
        path=folder,
        spec_path=spec_path,
        expected_requirements=[
            ExpectedRequirement(**item) for item in data.get("expected_requirements", [])
        ],
        expected_defects=[
            ExpectedDefect(**item) for item in data.get("expected_defects", [])
        ],
        prefab_requirements_path=prefab if prefab.exists() else None,
    )


def load_prefab_requirements(path: Path) -> list[Requirement]:
    """Read the deterministic Requirement fixtures used by --static-only mode."""
    with path.open() as f:
        data = json.load(f)
    reqs: list[Requirement] = []
    for item in data["requirements"]:
        reqs.append(
            Requirement(
                external_id=item["external_id"],
                kind=RequirementKind(item["kind"]),
                title=item["title"],
                statement=item["statement"],
                priority=item.get("priority", 3),
                source_document_id=item["source_document_id"],
                source_chunk_ids=item.get("source_chunk_ids", []),
            )
        )
    return reqs


def discover_benchmarks(root: Path) -> list[Path]:
    """Return every folder under `root` that contains an `expected.yaml`."""
    if not root.exists():
        return []
    return sorted(
        p.parent for p in root.glob("*/expected.yaml") if p.is_file()
    )
