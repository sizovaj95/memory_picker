"""End-to-end coverage for the Epic 1 pipeline."""

from __future__ import annotations

import logging
from datetime import datetime

from memory_picker.config import build_settings
from memory_picker.pipeline import run_pipeline
from tests.helpers import set_mtime, write_checkerboard_image, write_dark_image, write_text_file


def test_run_pipeline_moves_files_and_is_safe_on_rerun(tmp_path, caplog):
    root = tmp_path / "trip"
    root.mkdir()

    accepted_day_one = write_checkerboard_image(
        root / "accepted_day_one.jpg",
        capture_datetime=datetime(2026, 1, 2, 9, 30, 0),
    )
    rejected_day_one = write_dark_image(root / "rejected_day_one.jpg")
    accepted_day_two = write_checkerboard_image(root / "accepted_day_two.png")
    artifact = write_text_file(root / "clip.MOV", "video-placeholder")

    set_mtime(rejected_day_one, datetime(2026, 1, 2, 11, 0, 0))
    set_mtime(accepted_day_two, datetime(2026, 1, 3, 14, 0, 0))
    set_mtime(artifact, datetime(2026, 1, 2, 15, 0, 0))
    set_mtime(accepted_day_one, datetime(2026, 2, 1, 10, 0, 0))

    settings = build_settings(root)

    with caplog.at_level(logging.INFO, logger="memory_picker.pipeline"):
        summary = run_pipeline(settings)

    assert summary.total_items == 4
    assert summary.photo_items == 3
    assert summary.accepted_photos == 2
    assert summary.rejected_photos == 1
    assert summary.non_photo_items == 1
    assert summary.day_count == 2
    assert (root / "day01" / "accepted_day_one.jpg").exists()
    assert (root / "day01" / "rejected" / "rejected_day_one.jpg").exists()
    assert (root / "day01" / "not_photo" / "clip.MOV").exists()
    assert (root / "day02" / "accepted_day_two.png").exists()
    assert "Run summary" in caplog.text

    rerun_summary = run_pipeline(settings)
    assert rerun_summary.total_items == 0
    assert rerun_summary.moved_files == 0
