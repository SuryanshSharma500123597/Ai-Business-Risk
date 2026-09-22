"""structlog JSON logging with run correlation (docs/01_architecture/architecture.md §9).

Logs go to stdout as JSON; run_id/analysis_id are bound via contextvars so
every log line inside an analysis run is correlated.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from backend.core.config import get_settings


def configure_logging(level: str | None = None) -> None:
    log_level = (level or get_settings().log_level).upper()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)


def bind_run_id(run_id: str) -> None:
    structlog.contextvars.bind_contextvars(run_id=run_id)


def clear_run_context() -> None:
    structlog.contextvars.clear_contextvars()
