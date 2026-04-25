"""ARQ task functions registered in WorkerSettings."""

from ai_testplan_generator.jobs.tasks.autonomous import (
    delete_project_artefacts,
    run_autonomous,
)
from ai_testplan_generator.jobs.tasks.ingest import ingest_document

__all__ = [
    "delete_project_artefacts",
    "ingest_document",
    "run_autonomous",
]
