"""End-to-end coverage for the Epic 1 pipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime

from memory_picker.config import build_settings
from memory_picker.pipeline import run_pipeline
from tests.helpers import (
    FilenameMockEmbedder,
    MockClusterCategorizer,
    set_mtime,
    write_checkerboard_image,
    write_dark_image,
    write_text_file,
)


def test_run_pipeline_moves_files_and_is_safe_on_rerun(tmp_path, caplog):
    root = tmp_path / "trip"
    root.mkdir()

    accepted_day_one = write_checkerboard_image(
        root / "accepted_day_one.jpg",
        capture_datetime=datetime(2026, 1, 2, 9, 30, 0),
    )
    accepted_day_one_variant = write_checkerboard_image(root / "accepted_day_one_variant.jpg")
    rejected_day_one = write_dark_image(root / "rejected_day_one.jpg")
    accepted_day_two = write_checkerboard_image(root / "accepted_day_two.png")
    artifact = write_text_file(root / "clip.MOV", "video-placeholder")

    set_mtime(accepted_day_one_variant, datetime(2026, 1, 2, 9, 30, 40))
    set_mtime(rejected_day_one, datetime(2026, 1, 2, 11, 0, 0))
    set_mtime(accepted_day_two, datetime(2026, 1, 3, 14, 0, 0))
    set_mtime(artifact, datetime(2026, 1, 2, 15, 0, 0))
    set_mtime(accepted_day_one, datetime(2026, 2, 1, 10, 0, 0))

    settings = build_settings(root)
    embedder = FilenameMockEmbedder(
        {
            "accepted_day_one.jpg": [1.0, 0.0, 0.0],
            "accepted_day_one_variant.jpg": [0.99, 0.01, 0.0],
            "accepted_day_two.png": [0.0, 1.0, 0.0],
            "c001_b001_001.jpg": [1.0, 0.0, 0.0],
            "c001_b001_001.png": [0.0, 1.0, 0.0],
        }
    )

    with caplog.at_level(logging.INFO, logger="memory_picker.pipeline"):
        summary = run_pipeline(settings, embedder=embedder)

    assert summary.total_items == 5
    assert summary.photo_items == 4
    assert summary.accepted_photos == 3
    assert summary.rejected_photos == 1
    assert summary.non_photo_items == 1
    assert summary.day_count == 2
    assert (root / "day01" / "c001_b001_001.jpg").exists()
    assert not (root / "day01" / "accepted_day_one.jpg").exists()
    assert not (root / "day01" / "accepted_day_one_variant.jpg").exists()
    assert (root / "day01" / "rejected" / "rejected_day_one.jpg").exists()
    assert (root / "day01" / "rejected" / "accepted_day_one_variant.jpg").exists()
    assert (root / "day01" / "not_photo" / "clip.MOV").exists()
    assert (root / "day02" / "c001_b001_001.png").exists()
    assert (root / "day01" / "cluster_manifest.json").exists()
    assert (root / "day02" / "cluster_manifest.json").exists()
    day_one_manifest = json.loads((root / "day01" / "cluster_manifest.json").read_text(encoding="utf-8"))
    assert day_one_manifest["summary"]["accepted_photo_count"] == 1
    assert day_one_manifest["clusters"][0]["member_filenames"] == ["c001_b001_001.jpg"]
    assert day_one_manifest["clusters"][0]["representative_filename"] == "c001_b001_001.jpg"
    assert summary.clustered_days == 2
    assert summary.final_cluster_count == 2
    assert summary.duplicate_photos_rejected == 1
    assert summary.renamed_photos == 2
    assert summary.cleanup_manifests_rewritten == 2
    assert "Run summary" in caplog.text

    rerun_summary = run_pipeline(settings, embedder=embedder)
    assert rerun_summary.total_items == 0
    assert rerun_summary.moved_files == 0
    assert rerun_summary.clustered_days == 2
    assert rerun_summary.duplicate_photos_rejected == 0
    assert rerun_summary.renamed_photos == 0


def test_run_pipeline_optionally_categorizes_clusters_and_is_safe_on_rerun(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()

    accepted_day_one = write_checkerboard_image(
        root / "accepted_day_one.jpg",
        capture_datetime=datetime(2026, 1, 2, 9, 30, 0),
    )
    accepted_day_one_variant = write_checkerboard_image(root / "accepted_day_one_variant.jpg")
    accepted_day_two = write_checkerboard_image(root / "accepted_day_two.png")

    set_mtime(accepted_day_one_variant, datetime(2026, 1, 2, 9, 30, 40))
    set_mtime(accepted_day_two, datetime(2026, 1, 3, 14, 0, 0))
    set_mtime(accepted_day_one, datetime(2026, 2, 1, 10, 0, 0))

    base_settings = build_settings(root)
    settings = replace(
        base_settings,
        categorization_settings=replace(
            base_settings.categorization_settings,
            enabled=True,
        ),
    )
    embedder = FilenameMockEmbedder(
        {
            "accepted_day_one.jpg": [1.0, 0.0, 0.0],
            "accepted_day_one_variant.jpg": [0.99, 0.01, 0.0],
            "accepted_day_two.png": [0.0, 1.0, 0.0],
            "c001_b001_001.jpg": [1.0, 0.0, 0.0],
            "c001_b001_001.png": [0.0, 1.0, 0.0],
        }
    )
    categorizer = MockClusterCategorizer(
        categories_by_cluster_id={
            "cluster001": "architecture",
        }
    )

    summary = run_pipeline(settings, embedder=embedder, categorizer=categorizer)

    assert summary.classified_clusters == 2
    assert summary.categorized_days == 2
    assert summary.categorized_photos_moved == 2
    assert categorizer.calls == [
        ("day01", "cluster001", "c001_b001_001.jpg"),
        ("day02", "cluster001", "c001_b001_001.png"),
    ]
    assert (root / "day01" / "architecture" / "c001_b001_001.jpg").exists()
    assert (root / "day02" / "architecture" / "c001_b001_001.png").exists()

    day_one_manifest = json.loads((root / "day01" / "cluster_manifest.json").read_text(encoding="utf-8"))
    assert day_one_manifest["clusters"][0]["category_name"] == "architecture"
    assert (
        day_one_manifest["clusters"][0]["members"][0]["relative_path"]
        == "day01/architecture/c001_b001_001.jpg"
    )

    rerun_categorizer = MockClusterCategorizer(
        categories_by_cluster_id={
            "cluster001": "architecture",
        }
    )
    rerun_summary = run_pipeline(settings, embedder=embedder, categorizer=rerun_categorizer)

    assert rerun_summary.classified_clusters == 2
    assert rerun_summary.categorized_days == 2
    assert (root / "day01" / "architecture" / "c001_b001_001.jpg").exists()
    assert (root / "day02" / "architecture" / "c001_b001_001.png").exists()
