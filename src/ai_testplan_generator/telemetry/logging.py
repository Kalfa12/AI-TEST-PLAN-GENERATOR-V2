"""Structured logging configuration (M22).

Configures structlog with either a JSON renderer (LOG_FORMAT=json, for
production log shipping) or a human-readable console renderer (default).

When OTEL_ENABLED=true the request middleware injects trace_id and span_id
via structlog.contextvars so every log line carries trace correlation without
any extra code in individual log calls.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ai_testplan_generator.config import Settings


def configure_logging(settings: "Settings") -> None:
    """Apply structlog configuration based on *settings*.

    Must be called early in application startup (before any log calls) from
    both ``create_app()`` and the ARQ worker ``startup()`` hook.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        final_processor: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.ExceptionPrettyPrinter(),
            final_processor,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Mirror level to stdlib so third-party libraries (uvicorn, arq, etc.)
    # respect the same threshold.
    logging.basicConfig(level=level, stream=sys.stderr, format="%(message)s")
