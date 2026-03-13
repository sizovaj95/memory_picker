"""Tests for safe file moves."""

from __future__ import annotations

from memory_picker.config import build_settings
from memory_picker.file_actions import apply_move_plans
from memory_picker.models import DestinationCategory, FileMovePlan


def test_apply_move_plans_creates_expected_day_structure(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()

    accepted = root / "good.jpg"
    rejected = root / "bad.jpg"
    artifact = root / "clip.mov"
    accepted.write_text("good", encoding="utf-8")
    rejected.write_text("bad", encoding="utf-8")
    artifact.write_text("artifact", encoding="utf-8")

    summary = apply_move_plans(
        build_settings(root),
        [
            FileMovePlan(accepted, "day01", DestinationCategory.ACCEPTED),
            FileMovePlan(rejected, "day01", DestinationCategory.REJECTED),
            FileMovePlan(artifact, "day01", DestinationCategory.NOT_PHOTO),
        ],
    )

    assert summary.accepted_moved == 1
    assert summary.rejected_moved == 1
    assert summary.artifacts_moved == 1
    assert (root / "day01" / "good.jpg").exists()
    assert (root / "day01" / "rejected" / "bad.jpg").exists()
    assert (root / "day01" / "not_photo" / "clip.mov").exists()


def test_apply_move_plans_is_collision_safe(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()
    existing_day = root / "day01"
    existing_day.mkdir()
    (existing_day / "photo.jpg").write_text("existing", encoding="utf-8")

    source = root / "photo.jpg"
    source.write_text("incoming", encoding="utf-8")

    summary = apply_move_plans(
        build_settings(root),
        [FileMovePlan(source, "day01", DestinationCategory.ACCEPTED)],
    )

    assert summary.accepted_moved == 1
    assert (existing_day / "photo.jpg").read_text(encoding="utf-8") == "existing"
    assert (existing_day / "photo__dup01.jpg").read_text(encoding="utf-8") == "incoming"
