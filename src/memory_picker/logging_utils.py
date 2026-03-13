"""Shared logging configuration."""

from __future__ import annotations

import logging


def configure_logging(level: int | str = logging.INFO) -> logging.Logger:
    """Configure package logging once and return the package logger."""

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )

    logger = logging.getLogger("memory_picker")
    logger.setLevel(level)
    return logger
