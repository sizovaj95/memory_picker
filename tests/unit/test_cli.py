"""Tests for the terminal CLI flow."""

from __future__ import annotations

import memory_picker.cli as cli_module
from memory_picker.config import build_settings
from memory_picker.models import HeifConversionSummary, RunSummary


def test_main_interactive_convert_only_prints_conversion_summary(tmp_path, monkeypatch, capsys):
    photos_root = tmp_path / "photos"
    photos_root.mkdir()
    trip_root = photos_root / "trip-one"
    trip_root.mkdir()

    monkeypatch.setattr(cli_module, "prompt_for_trip_root", lambda: trip_root)
    monkeypatch.setattr(cli_module, "prompt_yes_no", lambda _prompt, default: True)

    captured_roots: list[str] = []

    def fake_build_settings(root):
        captured_roots.append(str(root))
        return build_settings(root)

    def fake_convert(settings):
        return HeifConversionSummary(converted_files=3, deleted_original_files=3)

    monkeypatch.setattr(cli_module, "build_settings", fake_build_settings)
    monkeypatch.setattr(cli_module, "convert_trip_root_heif_files", fake_convert)

    exit_code = cli_module.main([])

    assert exit_code == 0
    assert captured_roots == [str(trip_root)]
    output = capsys.readouterr().out
    assert "HEIF conversion summary" in output
    assert "converted_heif_files: 3" in output


def test_main_interactive_full_pipeline_enables_categorization_and_prints_warning(
    tmp_path,
    monkeypatch,
    capsys,
):
    photos_root = tmp_path / "photos"
    photos_root.mkdir()
    trip_root = photos_root / "trip-two"
    trip_root.mkdir()

    monkeypatch.setattr(cli_module, "prompt_for_trip_root", lambda: trip_root)
    responses = iter([False, True])
    monkeypatch.setattr(cli_module, "prompt_yes_no", lambda _prompt, default: next(responses))

    captured_settings = []

    def fake_run_pipeline(settings):
        captured_settings.append(settings)
        return RunSummary(
            total_items=2,
            photo_items=2,
            non_photo_items=0,
            unsupported_items=0,
            converted_heif_files=0,
            deleted_original_heif_files=0,
            accepted_photos=2,
            rejected_photos=0,
            day_count=1,
            moved_files=2,
            created_directories=1,
        )

    monkeypatch.setattr(cli_module, "run_pipeline", fake_run_pipeline)

    exit_code = cli_module.main([])

    assert exit_code == 0
    assert len(captured_settings) == 1
    assert captured_settings[0].categorization_settings.enabled is True
    output = capsys.readouterr().out
    assert "Turn VPN off before OpenAI categorization." in output
    assert "people" in output
    assert "architecture" in output
    assert "Memory Picker run summary" in output


def test_prompt_for_trip_root_uses_questionary_text_prompt(tmp_path, monkeypatch, capsys):
    photos_root = tmp_path / "photos"
    photos_root.mkdir()
    trip_root = photos_root / "trip-four"
    trip_root.mkdir()

    monkeypatch.setattr(cli_module, "WINDOWS_PHOTO_ROOT", photos_root)

    class DummyPrompt:
        def __init__(self, responses):
            self._responses = responses

        def ask(self):
            return next(self._responses)

    class DummyQuestionary:
        def __init__(self, responses):
            self._responses = responses

        def text(self, _message):
            return DummyPrompt(self._responses)

        def select(self, *_args, **_kwargs):
            raise AssertionError("select should not be used in this test")

    responses = iter(["missing-folder", "trip-four"])
    monkeypatch.setattr(cli_module, "_require_questionary", lambda: DummyQuestionary(responses))

    selected_path = cli_module.prompt_for_trip_root()

    assert selected_path == trip_root
    output = capsys.readouterr().out
    assert "Folder not found" in output


def test_prompt_yes_no_uses_questionary_select_default_selection(monkeypatch):
    observed_defaults = []

    class DummyPrompt:
        def __init__(self, value):
            self._value = value

        def ask(self):
            return self._value

    class DummyQuestionary:
        def text(self, *_args, **_kwargs):
            raise AssertionError("text should not be used in this test")

        def select(self, _message, **kwargs):
            observed_defaults.append(kwargs["default"])
            return DummyPrompt("No")

    monkeypatch.setattr(cli_module, "_require_questionary", lambda: DummyQuestionary())

    result = cli_module.prompt_yes_no("Apply categorization?", default=True)

    assert result is False
    assert observed_defaults == ["Yes"]


def test_main_with_root_flag_keeps_noninteractive_flow(tmp_path, monkeypatch, capsys):
    trip_root = tmp_path / "trip-three"
    trip_root.mkdir()

    captured_settings = []

    def fake_run_pipeline(settings):
        captured_settings.append(settings)
        return RunSummary(
            total_items=0,
            photo_items=0,
            non_photo_items=0,
            unsupported_items=0,
            converted_heif_files=0,
            deleted_original_heif_files=0,
            accepted_photos=0,
            rejected_photos=0,
            day_count=0,
            moved_files=0,
            created_directories=0,
        )

    monkeypatch.setattr(cli_module, "run_pipeline", fake_run_pipeline)

    exit_code = cli_module.main(["--root", str(trip_root)])

    assert exit_code == 0
    assert len(captured_settings) == 1
    assert captured_settings[0].root_path == trip_root.resolve()
    output = capsys.readouterr().out
    assert "Memory Picker run summary" in output
