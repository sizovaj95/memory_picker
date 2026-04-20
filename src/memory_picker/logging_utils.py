"""Shared logging configuration."""

from __future__ import annotations

import logging

QUIET_THIRD_PARTY_LOGGERS = (
    "openai",
    "httpx",
    "httpcore",
)
PROGRESS_LOG_INTERVAL = 20


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


def log_progress(
    logger: logging.Logger,
    action: str,
    index: int,
    total: int,
    *,
    noun: str = "file",
    interval: int = PROGRESS_LOG_INTERVAL,
) -> None:
    """Log periodic progress for long-running per-item work."""

    if total <= 0:
        return
    if index == total or index % interval == 0:
        logger.info("%s %s number %s/%s", action, noun, index, total)
