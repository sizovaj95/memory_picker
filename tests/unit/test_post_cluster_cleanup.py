"""Tests for deterministic post-cluster duplicate cleanup."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from memory_picker.config import build_settings
from memory_picker.post_cluster_cleanup import run_post_cluster_cleanup
from tests.helpers import write_checkerboard_image, write_color_block_image


def test_run_post_cluster_cleanup_rejects_duplicate_losers_and_rewrites_manifest(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    rejected_path = day_path / "rejected"
    rejected_path.mkdir(parents=True)

    write_checkerboard_image(day_path / "a.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 0))
    write_checkerboard_image(day_path / "b.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 1))
    write_checkerboard_image(day_path / "c.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 2))
    _write_cluster_manifest(
        day_path,
        {
            "day_name": "day01",
            "manifest_version": 1,
            "summary": {
                "accepted_photo_count": 3,
                "burst_group_count": 1,
                "cluster_count": 1,
                "singleton_cluster_count": 0,
            },
            "burst_groups": [
                {
                    "burst_group_id": "burst001",
                    "representative_filename": "a.jpg",
                    "member_filenames": ["a.jpg", "b.jpg", "c.jpg"],
                    "member_count": 3,
                }
            ],
            "clusters": [
                {
                    "cluster_id": "cluster001",
                    "representative_filename": "a.jpg",
                    "member_filenames": ["a.jpg", "b.jpg", "c.jpg"],
                    "burst_group_ids": ["burst001"],
                    "member_count": 3,
                    "members": [
                        _build_member("a.jpg", "burst001", "2026-01-01T10:00:00", 10.0, 0.0),
                        _build_member("b.jpg", "burst001", "2026-01-01T10:00:01", 25.0, 0.1),
                        _build_member("c.jpg", "burst001", "2026-01-01T10:00:02", 15.0, 0.2),
                    ],
                }
            ],
            "generated_from": str(day_path),
        },
    )

    summary = run_post_cluster_cleanup(build_settings(root))

    assert summary.processed_days == 1
    assert summary.duplicate_photos_rejected == 2
    assert summary.renamed_photos == 1
    assert (day_path / "c001_b001_001.jpg").exists()
    assert not (day_path / "a.jpg").exists()
    assert not (day_path / "b.jpg").exists()
    assert not (day_path / "c.jpg").exists()
    assert (rejected_path / "a.jpg").exists()
    assert (rejected_path / "c.jpg").exists()

    payload = json.loads((day_path / "cluster_manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["accepted_photo_count"] == 1
    assert payload["summary"]["singleton_cluster_count"] == 1
    assert payload["clusters"][0]["representative_filename"] == "c001_b001_001.jpg"
    assert payload["clusters"][0]["member_filenames"] == ["c001_b001_001.jpg"]


def test_run_post_cluster_cleanup_does_not_deduplicate_across_burst_groups(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)

    write_checkerboard_image(day_path / "a.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 0))
    write_checkerboard_image(day_path / "b.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 1))
    _write_cluster_manifest(
        day_path,
        {
            "day_name": "day01",
            "manifest_version": 1,
            "summary": {
                "accepted_photo_count": 2,
                "burst_group_count": 2,
                "cluster_count": 1,
                "singleton_cluster_count": 0,
            },
            "burst_groups": [
                {
                    "burst_group_id": "burst001",
                    "representative_filename": "a.jpg",
                    "member_filenames": ["a.jpg"],
                    "member_count": 1,
                },
                {
                    "burst_group_id": "burst002",
                    "representative_filename": "b.jpg",
                    "member_filenames": ["b.jpg"],
                    "member_count": 1,
                },
            ],
            "clusters": [
                {
                    "cluster_id": "cluster001",
                    "representative_filename": "a.jpg",
                    "member_filenames": ["a.jpg", "b.jpg"],
                    "burst_group_ids": ["burst001", "burst002"],
                    "member_count": 2,
                    "members": [
                        _build_member("a.jpg", "burst001", "2026-01-01T10:00:00", 10.0, 0.0),
                        _build_member("b.jpg", "burst002", "2026-01-01T10:00:01", 20.0, 0.1),
                    ],
                }
            ],
            "generated_from": str(day_path),
        },
    )

    summary = run_post_cluster_cleanup(build_settings(root))

    assert summary.duplicate_photos_rejected == 0
    assert summary.renamed_photos == 2
    assert (day_path / "c001_b001_001.jpg").exists()
    assert (day_path / "c001_b002_001.jpg").exists()


def test_run_post_cluster_cleanup_does_not_deduplicate_across_clusters(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)

    write_color_block_image(day_path / "a.jpg", (10, 20, 30))
    write_color_block_image(day_path / "b.jpg", (10, 20, 30))
    _write_cluster_manifest(
        day_path,
        {
            "day_name": "day01",
            "manifest_version": 1,
            "summary": {
                "accepted_photo_count": 2,
                "burst_group_count": 2,
                "cluster_count": 2,
                "singleton_cluster_count": 2,
            },
            "burst_groups": [
                {
                    "burst_group_id": "burst001",
                    "representative_filename": "a.jpg",
                    "member_filenames": ["a.jpg"],
                    "member_count": 1,
                },
                {
                    "burst_group_id": "burst002",
                    "representative_filename": "b.jpg",
                    "member_filenames": ["b.jpg"],
                    "member_count": 1,
                },
            ],
            "clusters": [
                {
                    "cluster_id": "cluster001",
                    "representative_filename": "a.jpg",
                    "member_filenames": ["a.jpg"],
                    "burst_group_ids": ["burst001"],
                    "member_count": 1,
                    "members": [
                        _build_member("a.jpg", "burst001", "2026-01-01T10:00:00", 10.0, 0.0),
                    ],
                },
                {
                    "cluster_id": "cluster002",
                    "representative_filename": "b.jpg",
                    "member_filenames": ["b.jpg"],
                    "burst_group_ids": ["burst002"],
                    "member_count": 1,
                    "members": [
                        _build_member("b.jpg", "burst002", "2026-01-01T10:00:01", 20.0, 0.0),
                    ],
                },
            ],
            "generated_from": str(day_path),
        },
    )

    summary = run_post_cluster_cleanup(build_settings(root))

    assert summary.duplicate_photos_rejected == 0
    assert (day_path / "c001_b001_001.jpg").exists()
    assert (day_path / "c002_b002_001.jpg").exists()


def _build_member(
    filename: str,
    burst_group_id: str,
    captured_at: str,
    blur_score: float,
    cosine_distance_to_representative: float,
) -> dict:
    return {
        "filename": filename,
        "relative_path": str(Path("day01") / filename),
        "burst_group_id": burst_group_id,
        "captured_at": captured_at,
        "orientation": "landscape",
        "blur_score": blur_score,
        "brightness_mean": 100.0,
        "overexposed_ratio": 0.1,
        "cosine_distance_to_representative": cosine_distance_to_representative,
        "histogram_similarity_to_representative": 1.0,
        "perceptual_hash_distance_to_representative": 0,
    }


def _write_cluster_manifest(day_path: Path, payload: dict) -> None:
    (day_path / "cluster_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
