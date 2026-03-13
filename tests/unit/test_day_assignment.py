"""Tests for EXIF/mtime day assignment."""

from __future__ import annotations

from datetime import datetime

from memory_picker.config import build_settings
from memory_picker.day_assignment import build_day_assignments, build_day_map, resolve_photo_record
from memory_picker.inventory import scan_trip_root
from memory_picker.models import TimestampSource
from tests.helpers import set_mtime, write_checkerboard_image


def test_day_assignment_prefers_exif_and_falls_back_to_mtime(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()

    exif_photo = write_checkerboard_image(
        root / "exif.jpg",
        capture_datetime=datetime(2026, 1, 2, 10, 30, 0),
    )
    fallback_photo = write_checkerboard_image(root / "fallback.jpg")
    same_day_photo = write_checkerboard_image(
        root / "same_day.jpg",
        capture_datetime=datetime(2026, 1, 2, 17, 15, 0),
    )

    set_mtime(exif_photo, datetime(2026, 2, 1, 8, 0, 0))
    set_mtime(fallback_photo, datetime(2026, 1, 1, 12, 0, 0))
    set_mtime(same_day_photo, datetime(2026, 3, 1, 9, 0, 0))

    settings = build_settings(root)
    photo_items = scan_trip_root(settings)
    photo_records = [resolve_photo_record(item) for item in photo_items]
    day_map = build_day_map([record.captured_on for record in photo_records], settings)
    assignments = build_day_assignments(photo_records, day_map)

    records_by_name = {record.source_path.name: record for record in photo_records}
    assignments_by_name = {assignment.source_path.name: assignment for assignment in assignments}

    assert records_by_name["exif.jpg"].timestamp_source == TimestampSource.EXIF
    assert records_by_name["exif.jpg"].captured_on.isoformat() == "2026-01-02"
    assert records_by_name["fallback.jpg"].timestamp_source == TimestampSource.MTIME
    assert records_by_name["fallback.jpg"].captured_on.isoformat() == "2026-01-01"
    assert assignments_by_name["fallback.jpg"].day_name == "day01"
    assert assignments_by_name["exif.jpg"].day_name == "day02"
    assert assignments_by_name["same_day.jpg"].day_name == "day02"

    rerun_day_map = build_day_map([record.captured_on for record in photo_records], settings)
    assert day_map == rerun_day_map
