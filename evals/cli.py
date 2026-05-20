"""CLI entry point for the eval harness.

Usage:
  python -m evals.cli --static-only                  # all benchmarks, no LLM
  python -m evals.cli --full                         # all benchmarks, LLM
  python -m evals.cli --static-only synthetic_aerospace
  python -m evals.cli --static-only --json out.json --markdown out.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals.loader import discover_benchmarks, load_benchmark
from evals.report import diff_against_baseline, render_json, render_markdown
from evals.runner import run_many

_ROOT = Path(__file__).resolve().parent
_BENCH_DIR = _ROOT / "benchmarks"


def _resolve_benchmarks(names: list[str] | None) -> list[Path]:
    available = discover_benchmarks(_BENCH_DIR)
    if not names:
        return available
    by_name = {p.name: p for p in available}
    resolved: list[Path] = []
    for n in names:
        if n in by_name:
            resolved.append(by_name[n])
            continue
        # Allow passing a full path too.
        candidate = Path(n)
        if candidate.exists() and (candidate / "expected.yaml").exists():
            resolved.append(candidate)
            continue
        raise SystemExit(
            f"Unknown benchmark '{n}'. Available: {', '.join(by_name)}"
        )
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evals.cli",
        description="Run the AI Test Plan Generator evaluation harness.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--static-only",
        action="store_const",
        const="static-only",
        dest="mode",
        help="Run defect detection against prefab requirement fixtures. No LLM.",
    )
    mode.add_argument(
        "--full",
        action="store_const",
        const="full",
        dest="mode",
        help="Run the full ingestion + extraction pipeline. Requires LLM keys.",
    )
    parser.add_argument(
        "benchmarks",
        nargs="*",
        help="Specific benchmark names to run. Omit to run all.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Path to write the JSON snapshot.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        help="Path to write the Markdown report.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_ROOT / "baseline.json",
        help="Baseline JSON file. Defaults to evals/baseline.json. "
        "Used for regression detection. Pass a non-existent path to skip.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero if any benchmark regresses vs baseline.",
    )

    args = parser.parse_args(argv)

    folders = _resolve_benchmarks(args.benchmarks)
    if not folders:
        print(
            f"No benchmarks found under {_BENCH_DIR}. "
            "Create a folder with expected.yaml + spec to start.",
            file=sys.stderr,
        )
        return 1

    benchmarks = [load_benchmark(f) for f in folders]
    print(
        f"Running {len(benchmarks)} benchmark(s) in {args.mode} mode…",
        file=sys.stderr,
    )
    results = run_many(benchmarks, mode=args.mode)

    md = render_markdown(results)
    js = render_json(results)

    if args.markdown:
        args.markdown.write_text(md)
        print(f"Wrote Markdown report → {args.markdown}", file=sys.stderr)
    else:
        print(md)

    if args.json:
        args.json.write_text(js)
        print(f"Wrote JSON snapshot   → {args.json}", file=sys.stderr)

    regressions = diff_against_baseline(js, args.baseline)
    if regressions:
        print("\n" + regressions, file=sys.stderr)
        if args.fail_on_regression:
            return 2

    # Non-zero exit if any benchmark errored.
    if any(r.error for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
