"""Format BenchmarkResult lists into human + machine readable reports."""

from __future__ import annotations

import json
from pathlib import Path

from evals.runner import BenchmarkResult


def _fmt_pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def render_markdown(results: list[BenchmarkResult]) -> str:
    """Compact Markdown report for terminals and PR comments."""
    lines: list[str] = []
    lines.append("# Evaluation report\n")

    # Top-level summary table.
    lines.append("| Benchmark | Mode | Extract F1 | Defect recall | Time | Status |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        status = "✗ " + r.error if r.error else "✓"
        f1 = _fmt_pct(r.extraction.f1) if r.extraction else "—"
        defrec = _fmt_pct(r.defect_score.recall) if r.defect_score else "—"
        lines.append(
            f"| {r.benchmark.name} | {r.mode} | {f1} | {defrec} | {r.elapsed_s:.2f}s | {status} |"
        )
    lines.append("")

    # Per-benchmark detail.
    for r in results:
        lines.append(f"\n## {r.benchmark.name}\n")
        lines.append(f"_{r.benchmark.description.strip()}_\n")
        if r.error:
            lines.append(f"\n**ERROR:** `{r.error}`\n")
            continue

        if r.extraction:
            e = r.extraction
            lines.append(
                f"**Extraction** — precision {_fmt_pct(e.precision)}, "
                f"recall {_fmt_pct(e.recall)}, F1 {_fmt_pct(e.f1)} "
                f"({e.tp} TP / {e.fp} FP / {e.fn} FN) · "
                f"kind accuracy {_fmt_pct(e.kind_accuracy)}"
            )
            if e.missed:
                lines.append(f"\n_Missed:_ `{', '.join(e.missed)}`")
            if e.spurious:
                lines.append("\n_Spurious extractions:_")
                for s in e.spurious[:5]:
                    lines.append(f"  - {s}")
                if len(e.spurious) > 5:
                    lines.append(f"  - …and {len(e.spurious) - 5} more")
            lines.append("")

        if r.defect_score:
            d = r.defect_score
            lines.append(
                f"**Defect detection** — recall {_fmt_pct(d.recall)} "
                f"({d.detected} / {d.expected_total})"
            )
            if d.missed:
                lines.append("\n_Missed defects:_")
                for tid, dtype in d.missed:
                    lines.append(f"  - {tid} → `{dtype}`")
            lines.append("")

    return "\n".join(lines)


def render_json(results: list[BenchmarkResult]) -> str:
    """Machine-readable snapshot for baseline diffing."""
    payload = []
    for r in results:
        item: dict = {
            "name": r.benchmark.name,
            "mode": r.mode,
            "elapsed_s": round(r.elapsed_s, 3),
            "error": r.error,
        }
        if r.extraction:
            item["extraction"] = {
                "tp": r.extraction.tp,
                "fp": r.extraction.fp,
                "fn": r.extraction.fn,
                "precision": round(r.extraction.precision, 4),
                "recall": round(r.extraction.recall, 4),
                "f1": round(r.extraction.f1, 4),
                "kind_accuracy": round(r.extraction.kind_accuracy, 4),
            }
        if r.defect_score:
            item["defects"] = {
                "expected": r.defect_score.expected_total,
                "detected": r.defect_score.detected,
                "recall": round(r.defect_score.recall, 4),
                "missed": [
                    {"target": t, "type": d} for t, d in r.defect_score.missed
                ],
            }
        payload.append(item)
    return json.dumps(payload, indent=2)


def diff_against_baseline(
    current_json: str, baseline_path: Path
) -> str | None:
    """Compare current JSON against a stored baseline.

    Returns a Markdown diff if regressions are found, None otherwise.
    A regression is defined as F1 dropping by > 1pp or defect recall
    dropping by > 5pp for any benchmark present in both runs.
    """
    if not baseline_path.exists():
        return None
    try:
        baseline = json.loads(baseline_path.read_text())
        current = json.loads(current_json)
    except Exception as exc:
        return f"Could not load baseline: {exc}"

    baseline_by_name = {b["name"]: b for b in baseline}
    regressions: list[str] = []
    for cur in current:
        name = cur["name"]
        base = baseline_by_name.get(name)
        if base is None:
            continue
        if "extraction" in cur and "extraction" in base:
            d = cur["extraction"]["f1"] - base["extraction"]["f1"]
            if d < -0.01:
                regressions.append(
                    f"  - **{name}**: extraction F1 "
                    f"{base['extraction']['f1']:.3f} → {cur['extraction']['f1']:.3f} "
                    f"({d:+.3f})"
                )
        if "defects" in cur and "defects" in base:
            d = cur["defects"]["recall"] - base["defects"]["recall"]
            if d < -0.05:
                regressions.append(
                    f"  - **{name}**: defect recall "
                    f"{base['defects']['recall']:.3f} → {cur['defects']['recall']:.3f} "
                    f"({d:+.3f})"
                )
    if not regressions:
        return None
    return "## ⚠️ Regressions vs baseline\n\n" + "\n".join(regressions)
