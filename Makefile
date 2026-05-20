# Convenience targets. All commands assume you're in the repo root.

.PHONY: help test eval eval-full eval-baseline lint typecheck

help:
	@echo "Available targets:"
	@echo "  make test           Run the Python test suite (pytest)"
	@echo "  make eval           Run the eval harness in static-only mode (no LLM keys needed)"
	@echo "  make eval-full      Run the eval harness in full mode (requires LLM keys)"
	@echo "  make eval-baseline  Re-capture baseline.json from a successful static-only run"
	@echo "  make lint           Run ruff"
	@echo "  make typecheck      Run mypy"

test:
	python -m pytest tests/ -q

eval:
	python -m evals.cli --static-only

eval-full:
	python -m evals.cli --full

eval-baseline:
	python -m evals.cli --static-only \
	    --json evals/baseline.json \
	    --markdown evals/last-report.md

lint:
	ruff check src tests evals

typecheck:
	mypy src
