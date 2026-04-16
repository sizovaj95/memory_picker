"""Shared logging configuration."""

from __future__ import annotations

import logging

QUIET_THIRD_PARTY_LOGGERS = (
    "openai",
    "httpx",
    "httpcore",
)


def configure_logging(level: int | str = logging.INFO) -> logging.Logger:
    """Configure package logging once and return the package logger."""

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )

    logger = logging.getLogger("memory_picker")
    logger.setLevel(level)
    for logger_name in QUIET_THIRD_PARTY_LOGGERS:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
    return logger
