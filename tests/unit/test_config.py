"""Smoke tests for configuration setup."""

from __future__ import annotations

from memory_picker.config import build_settings


def test_build_settings_loads_defaults(tmp_path):
    settings = build_settings(tmp_path)

    assert settings.root_path == tmp_path.resolve()
    assert "jpg" in settings.supported_photo_extensions
    assert settings.managed_folders.rejected == "rejected"
    assert settings.quality_thresholds.blur_threshold > 0
    assert settings.selection_settings.openai_model == "gpt-4.1-mini"
