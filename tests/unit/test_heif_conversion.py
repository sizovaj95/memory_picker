"""Tests for mandatory trip-root HEIF conversion."""

from __future__ import annotations

from datetime import datetime

import pytest

from memory_picker.config import build_settings
from memory_picker.day_assignment import extract_capture_datetime
from memory_picker.heif_conversion import convert_trip_root_heif_files
from tests.helpers import set_mtime, write_checkerboard_image, write_disguised_heif_image


def test_convert_trip_root_heif_files_converts_and_preserves_metadata(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()

    source_path = write_disguised_heif_image(
        root / "memory.heic",
        capture_datetime=datetime(2026, 1, 2, 9, 30, 0),
    )
    set_mtime(source_path, datetime(2026, 1, 4, 12, 0, 0))

    summary = convert_trip_root_heif_files(build_settings(root))

    converted_path = root / "memory.jpg"
    assert summary.converted_files == 1
    assert summary.deleted_original_files == 1
    assert converted_path.exists()
    assert not source_path.exists()
    assert extract_capture_datetime(converted_path) == datetime(2026, 1, 2, 9, 30, 0)
    assert converted_path.stat().st_mtime == pytest.approx(
        datetime(2026, 1, 4, 12, 0, 0).timestamp(),
        abs=0.01,
    )


def test_convert_trip_root_heif_files_uses_suffix_on_jpg_collision(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()

    write_checkerboard_image(root / "memory.jpg")
    source_path = write_disguised_heif_image(root / "memory.heif")

    summary = convert_trip_root_heif_files(build_settings(root))

    assert summary.converted_files == 1
    assert not source_path.exists()
    assert (root / "memory.jpg").exists()
    assert (root / "memory__converted01.jpg").exists()


def test_convert_trip_root_heif_files_keeps_original_when_conversion_fails(tmp_path, monkeypatch):
    root = tmp_path / "trip"
    root.mkdir()

    source_path = write_disguised_heif_image(root / "broken.heic")

    def fail_conversion(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("memory_picker.heif_conversion.Image.open", fail_conversion)

    with pytest.raises(OSError, match="boom"):
        convert_trip_root_heif_files(build_settings(root))

    assert source_path.exists()
    assert not (root / "broken.jpg").exists()
