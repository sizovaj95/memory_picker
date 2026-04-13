"""Shared logging configuration."""

from __future__ import annotations

import logging
import re

_BASE64_DATA_URL_RE = re.compile(
    r"data:image/[-+.a-zA-Z0-9]+;base64,[A-Za-z0-9+/=]+",
)


def sanitize_log_message(message: str) -> str:
    """Redact large inline image payloads from debug logs."""

    return _BASE64_DATA_URL_RE.sub("data:image/<redacted>;base64,<redacted>", message)


class _RedactingLogFilter(logging.Filter):
    """Remove sensitive or noisy inline payloads before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        sanitized = sanitize_log_message(rendered)
        if sanitized != rendered:
            record.msg = sanitized
            record.args = ()
        return True


def _install_redaction_filters() -> None:
    """Ensure root handlers redact oversized inline payloads."""

    redaction_filter = _RedactingLogFilter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(existing, _RedactingLogFilter) for existing in handler.filters):
            handler.addFilter(redaction_filter)


def configure_logging(level: int | str = logging.INFO) -> logging.Logger:
    """Configure package logging once and return the package logger."""

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )

    _install_redaction_filters()
    logger = logging.getLogger("memory_picker")
    logger.setLevel(level)
    return logger
