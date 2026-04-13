"""Tests for logging redaction helpers."""

from __future__ import annotations

from memory_picker.logging_utils import sanitize_log_message


def test_sanitize_log_message_redacts_inline_base64_image_urls():
    message = (
        "payload={'url': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAADabc123==', "
        "'detail': 'low'}"
    )

    sanitized = sanitize_log_message(message)

    assert "abc123" not in sanitized
    assert "data:image/<redacted>;base64,<redacted>" in sanitized
