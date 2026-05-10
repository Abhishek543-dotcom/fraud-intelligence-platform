"""Structured logging configuration shared across all Python services."""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(service_name: str, log_level: str = "INFO") -> structlog.BoundLogger:
    """Configure structured logging for a service.

    Args:
        service_name: Name of the service for log correlation.
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR).

    Returns:
        A configured structlog bound logger.
    """
    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Configure structlog processors
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.EventRenamer("msg"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger(service_name)
    logger = logger.bind(service=service_name)
    return logger
