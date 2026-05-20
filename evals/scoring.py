"""Scoring primitives for the eval harness.

Two scorers:
 - `score_extraction`  — precision/recall/F1 of requirement extraction against
                         expected_requirements in a benchmark
 - `score_defects`     — recall of static + LLM defect detection against
                         expected_defects

Both return small typed dataclasses so the report layer doesn't have to
guess at the shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ai_testplan_generator.models import (
    DefectInstance,
    Requirement,
    RequirementKind,
)


@dataclass(frozen=True)
class ExpectedRequirement:
    external_id: str
    kind: str
    statement_excerpt: str


@dataclass(frozen=True)
class ExpectedDefect:
    target_external_id: str
    defect_type: str


@dataclass
class ExtractionScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    kind_matches: int = 0
    kind_mismatches: int = 0
    matched_pairs: list[tuple[str, str]] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    spurious: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    @property
    def kind_accuracy(self) -> float:
        total = self.kind_matches + self.kind_mismatches
        return self.kind_matches / total if total else 0.0


@dataclass
class DefectScore:
    expected_total: int = 0
    detected: int = 0
    matched_pairs: list[tuple[str, str]] = field(default_factory=list)
    missed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.detected / self.expected_total if self.expected_total else 0.0


# ---------------------------------------------------------------------------
# Extraction scoring
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def score_extraction(
    extracted: Iterable[Requirement],
    expected: Iterable[ExpectedRequirement],
) -> ExtractionScore:
    """Match each expected requirement to at most one extracted one.

    The match key is the expected `statement_excerpt` — a case-insensitive,
    whitespace-normalised substring of the extracted requirement's statement.
    This is deliberately fuzzy: the LLM paraphrases, so an exact-match scorer
    would always read 0 / 100.

    Once an extracted requirement is claimed by an expected one, it cannot be
    matched again (prevents one over-eager LLM output from satisfying every
    expectation).
    """
    expected_list = list(expected)
    extracted_list = list(extracted)
    score = ExtractionScore()

    claimed: set[int] = set()
    for exp in expected_list:
        needle = _norm(exp.statement_excerpt)
        match_idx: int | None = None
        for idx, req in enumerate(extracted_list):
            if idx in claimed:
                continue
            haystack = _norm(req.statement)
            if needle in haystack:
                match_idx = idx
                break
        if match_idx is None:
            score.fn += 1
            score.missed.append(exp.external_id)
            continue
        claimed.add(match_idx)
        matched = extracted_list[match_idx]
        score.tp += 1
        score.matched_pairs.append((exp.external_id, matched.id))
        # Kind correctness — only counted on matches.
        try:
            expected_kind = RequirementKind(exp.kind)
            if matched.kind == expected_kind:
                score.kind_matches += 1
            else:
                score.kind_mismatches += 1
        except ValueError:
            # Expected kind not in the enum — record as mismatch but don't crash.
            score.kind_mismatches += 1

    score.fp = len(extracted_list) - len(claimed)
    score.spurious = [
        f"{r.id}: {r.statement[:80]}"
        for idx, r in enumerate(extracted_list)
        if idx not in claimed
    ]
    return score


# ---------------------------------------------------------------------------
# Defect scoring
# ---------------------------------------------------------------------------


def score_defects(
    detected: Iterable[DefectInstance],
    expected: Iterable[ExpectedDefect],
    *,
    # Map from spec external_id (REQ-009) to the actual req.id (req_abc123)
    # that the extractor / prefab produced. Defect instances reference
    # actual ids, not external ones.
    external_to_internal: dict[str, str],
) -> DefectScore:
    """Score how many expected (target, defect_type) pairs were detected.

    Precision is not scored — extra defects are not penalised in this
    version. The catalog is dense; counting false positives requires a
    fully-annotated spec which we don't have yet.
    """
    detected_pairs: set[tuple[str, str]] = set()
    for d in detected:
        detected_pairs.add((d.target_id, d.defect_type.value))

    score = DefectScore()
    expected_list = list(expected)
    score.expected_total = len(expected_list)

    for exp in expected_list:
        internal_id = external_to_internal.get(exp.target_external_id)
        if internal_id is None:
            score.missed.append((exp.target_external_id, exp.defect_type))
            continue
        if (internal_id, exp.defect_type) in detected_pairs:
            score.detected += 1
            score.matched_pairs.append((exp.target_external_id, exp.defect_type))
        else:
            score.missed.append((exp.target_external_id, exp.defect_type))

    return score
