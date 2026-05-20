"""Evaluation harness for the AI Test Plan Generator.

Two run modes:

  --static-only   Loads pre-extracted requirements from `prefab_requirements.json`
                  and runs the static defect detectors against them. No LLM
                  calls. Deterministic. Useful in CI and for anyone without
                  LLM keys configured.

  --full          Loads the spec file, runs the real ingestion pipeline
                  (loader + chunker + LLM extractor), then scores both
                  extraction precision/recall AND defect detection.
                  Requires LLM keys.

See `evals/README.md` for usage.
"""
