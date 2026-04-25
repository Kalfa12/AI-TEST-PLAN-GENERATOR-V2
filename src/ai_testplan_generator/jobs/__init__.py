"""Background job processing package (M17).

Entry points:
    - JobQueue / FakeJobQueue  — enqueue and inspect jobs
    - WorkerSettings           — ARQ worker configuration
    - arq ai_testplan_generator.jobs.worker.WorkerSettings  — run a worker
"""

from ai_testplan_generator.jobs.queue import (
    DeadLetterEntry,
    FakeJobQueue,
    JobQueue,
    JobQueueProtocol,
)

__all__ = [
    "DeadLetterEntry",
    "FakeJobQueue",
    "JobQueue",
    "JobQueueProtocol",
]
