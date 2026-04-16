"""Tests for Epic 2 accepted-photo preprocessing."""

from __future__ import annotations

from datetime import datetime

from memory_picker.config import build_settings
from memory_picker.models import Orientation
from memory_picker.preprocessing import load_day_photo_records
from tests.helpers import set_mtime, write_checkerboard_image, write_color_block_image, write_text_file


def test_load_day_photo_records_reads_accepted_images_recursively_and_skips_managed_dirs(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)
    (day_path / "rejected").mkdir()
    (day_path / "not_photo").mkdir()
    (day_path / "people").mkdir()

    accepted = write_checkerboard_image(day_path / "accepted.jpg")
    categorized = write_checkerboard_image(day_path / "people" / "categorized.jpg")
    write_checkerboard_image(day_path / "rejected" / "ignored.jpg")
    write_text_file(day_path / "cluster_manifest.json", "{}")
    write_text_file(day_path / "not_photo" / "clip.mov", "video")
    set_mtime(accepted, datetime(2026, 2, 3, 14, 0, 0))
    set_mtime(categorized, datetime(2026, 2, 3, 15, 0, 0))

    records = load_day_photo_records(day_path, build_settings(root))

    assert [record.filename for record in records] == ["accepted.jpg", "categorized.jpg"]
    assert records[0].day_name == "day01"
    assert records[0].relative_path.as_posix() == "day01/accepted.jpg"
    assert records[1].relative_path.as_posix() == "day01/people/categorized.jpg"


def test_load_day_photo_records_extracts_stable_descriptors(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)
    image_path = write_color_block_image(day_path / "landscape.png", (255, 0, 0), size=(160, 90))
    set_mtime(image_path, datetime(2026, 1, 1, 9, 0, 0))

    record = load_day_photo_records(day_path, build_settings(root))[0]

    assert record.orientation == Orientation.LANDSCAPE
    assert len(record.similarity_features.color_histogram) == 24
    assert record.similarity_features.perceptual_hash >= 0
    assert record.captured_at.isoformat().startswith("2026-01-01T09:00:00")
