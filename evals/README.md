# Evaluation harness

A small benchmark runner that scores the AI Test Plan Generator's
**requirement extraction** and **defect detection** against curated
specifications. Numbers replace vibes.

## Why

Without a benchmark, every prompt change is guesswork. With one, we can:

- Catch regressions before they hit users (compare each run against `baseline.json`).
- Pitch the product with real numbers (`extractor recall = 0.92 on the aerospace
  corpus`).
- Drive prompt-engineering work by what actually moves the needle.

## Two modes

| Mode | What it does | Needs LLM keys |
|---|---|---|
| `--static-only` | Loads pre-extracted fixtures, runs only static defect detectors. Deterministic. Use in CI. | No |
| `--full` | Loads the spec file, runs loader + chunker + LLM extractor, scores extraction AND defects. | Yes |

## Quick start

```bash
# One-time install of the harness extras (PyYAML).
pip install -e '.[evals]'

# Then from the repo root:
python -m evals.cli --static-only
# or
make eval
```

Output is a Markdown table with per-benchmark precision / recall / F1 plus
the list of missed defects. Pipe `--markdown report.md` and `--json
snapshot.json` to capture artefacts.

```bash
# Run only one benchmark
python -m evals.cli --static-only synthetic_aerospace

# Capture artefacts
python -m evals.cli --static-only \
  --markdown evals/last-report.md \
  --json evals/last-snapshot.json

# Fail the build if any benchmark regresses vs baseline
python -m evals.cli --static-only --fail-on-regression
```

## Adding a new benchmark

Each benchmark lives in its own folder under `evals/benchmarks/`:

```
evals/benchmarks/your_benchmark/
├── spec.md                      # or .pdf / .docx — the input
├── expected.yaml                # what the extractor + detectors should produce
└── prefab_requirements.json     # (optional) for --static-only mode
```

### `expected.yaml` schema

```yaml
name: My benchmark
description: One-line summary of what this benchmark stresses.
spec: spec.md            # path relative to this file

expected_requirements:
  - external_id: REQ-001
    kind: functional    # one of RequirementKind enum values
    statement_excerpt: regulate the line pressure within   # case-insensitive
                                                           # substring match

expected_defects:
  - target_external_id: REQ-003
    defect_type: modality_drift                 # DefectType enum value
```

### `prefab_requirements.json`

Mirror the requirements you expect the LLM extractor to produce, as
plain JSON. Used by `--static-only` to score the static checks without
spending tokens. Easy to author: copy the spec sentences in, fill in
the kind/priority/title fields.

## Current baseline

See [`baseline.json`](baseline.json) for the locked-in scores. Re-run
`python -m evals.cli --static-only --json evals/baseline.json` to update
when you've intentionally improved a detector.

## What the harness will not catch (yet)

- **Test case generation quality** — only extraction and defect detection are
  scored today. Scoring generated test cases requires either golden
  test-case fixtures or an LLM-judge layer; both are TODO.
- **LLM cost regressions** — token counts are not tracked yet. Adding
  this is one of the next items on `ROADMAP.md`.
- **End-to-end pipeline correctness** — the harness runs the extractor
  in isolation. The orchestrator's revision logic is exercised by the
  unit-test suite, not here.

## Known issues surfaced by the harness

The first run already turned up one real bug worth fixing:

> **`_check_modality` returns early on any `shall`**, so a compound
> requirement that mixes `should` and `shall` (e.g. REQ-009 in the
> synthetic_aerospace benchmark) escapes detection.
> Fix: detect modality drift per-clause, not per-statement, or rely on
> `_check_compound` to flag the mixed case first.

This is the kind of thing the harness will keep surfacing.
