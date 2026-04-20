"""Tests for pipeline helpers and orchestration details."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime

import memory_picker.pipeline as pipeline_module
from memory_picker.config import build_settings
from memory_picker.models import MediaClassification, MediaInventoryItem, PhotoRecord, QualityAssessment, TimestampSource


def test_run_quality_assessments_preserves_input_order_with_threads(tmp_path, monkeypatch):
    root = tmp_path / "trip"
    root.mkdir()
    photo_paths = [
        root / "slow.jpg",
        root / "fast.jpg",
        root / "medium.jpg",
    ]
    for path in photo_paths:
        path.write_text("placeholder", encoding="utf-8")

    sleep_by_name = {
        "slow.jpg": 0.03,
        "fast.jpg": 0.0,
        "medium.jpg": 0.01,
    }
    accepted_by_name = {
        "slow.jpg": True,
        "fast.jpg": False,
        "medium.jpg": True,
    }

    def fake_assess_photo(path, thresholds):
        time.sleep(sleep_by_name[path.name])
        return QualityAssessment(source_path=path, is_accepted=accepted_by_name[path.name])

    monkeypatch.setattr(pipeline_module, "assess_photo", fake_assess_photo)
    settings = build_settings(root)
    settings = replace(
        settings,
        quality_concurrency_settings=replace(
            settings.quality_concurrency_settings,
            max_workers=3,
        ),
    )

    assessments = pipeline_module._run_quality_assessments(
        [_build_photo_record(path) for path in photo_paths],
        settings,
    )

    assert [assessment.source_path.name for assessment in assessments] == [
        "slow.jpg",
        "fast.jpg",
        "medium.jpg",
    ]
    assert [assessment.is_accepted for assessment in assessments] == [True, False, True]


def _build_photo_record(path):
    item = MediaInventoryItem(
        source_path=path.resolve(),
        extension=path.suffix.lower().lstrip("."),
        size_bytes=path.stat().st_size,
        classification=MediaClassification.PHOTO,
    )
    captured_at = datetime(2026, 1, 1, 10, 0, 0)
    return PhotoRecord(
        inventory_item=item,
        captured_at=captured_at,
        captured_on=captured_at.date(),
        timestamp_source=TimestampSource.MTIME,
    )
