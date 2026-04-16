"""Tests for Epic 4 optional cluster categorization."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from memory_picker.categorization import (
    build_category_prompt,
    build_category_schema,
    run_cluster_categorization,
)
from memory_picker.config import build_settings
from tests.helpers import MockClusterCategorizer, write_checkerboard_image


def test_build_category_schema_uses_configured_category_names(tmp_path):
    settings = build_settings(tmp_path)

    schema = build_category_schema(settings.categorization_settings.categories)

    assert schema["properties"]["category_name"]["enum"] == [
        "people",
        "animals",
        "food",
        "nature",
        "city",
        "architecture",
        "other",
    ]


def test_build_category_prompt_includes_rule_text(tmp_path):
    settings = build_settings(tmp_path)

    prompt = build_category_prompt(settings.categorization_settings.categories)

    assert "architecture" in prompt
    assert "torii gates" in prompt.lower()
    assert "other" in prompt


def test_run_cluster_categorization_moves_accepted_photos_and_rewrites_manifest(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    (day_path / "rejected").mkdir(parents=True)
    (day_path / "not_photo").mkdir()
    write_checkerboard_image(day_path / "c001_b001_001.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 0))
    write_checkerboard_image(day_path / "c001_b002_001.jpg", capture_datetime=datetime(2026, 1, 1, 10, 1, 0))
    write_checkerboard_image(day_path / "c002_b002_001.jpg", capture_datetime=datetime(2026, 1, 1, 11, 0, 0))
    write_checkerboard_image(day_path / "rejected" / "ignore.jpg")
    write_checkerboard_image(day_path / "not_photo" / "also_ignore.jpg")
    _write_cluster_manifest(
        day_path,
        {
            "day_name": "day01",
            "manifest_version": 1,
            "summary": {
                "accepted_photo_count": 3,
                "burst_group_count": 3,
                "cluster_count": 2,
                "singleton_cluster_count": 1,
            },
            "burst_groups": [
                {
                    "burst_group_id": "burst001",
                    "representative_filename": "c001_b001_001.jpg",
                    "member_filenames": ["c001_b001_001.jpg"],
                    "member_count": 1,
                },
                {
                    "burst_group_id": "burst002",
                    "representative_filename": "c001_b002_001.jpg",
                    "member_filenames": ["c001_b002_001.jpg"],
                    "member_count": 1,
                },
                {
                    "burst_group_id": "burst003",
                    "representative_filename": "c002_b002_001.jpg",
                    "member_filenames": ["c002_b002_001.jpg"],
                    "member_count": 1,
                },
            ],
            "clusters": [
                {
                    "cluster_id": "cluster001",
                    "representative_filename": "c001_b001_001.jpg",
                    "member_filenames": ["c001_b001_001.jpg", "c001_b002_001.jpg"],
                    "burst_group_ids": ["burst001", "burst002"],
                    "member_count": 2,
                    "members": [
                        _build_member("c001_b001_001.jpg", "burst001", "2026-01-01T10:00:00"),
                        _build_member("c001_b002_001.jpg", "burst002", "2026-01-01T10:01:00"),
                    ],
                },
                {
                    "cluster_id": "cluster002",
                    "representative_filename": "c002_b002_001.jpg",
                    "member_filenames": ["c002_b002_001.jpg"],
                    "burst_group_ids": ["burst003"],
                    "member_count": 1,
                    "members": [
                        _build_member("c002_b002_001.jpg", "burst003", "2026-01-01T11:00:00"),
                    ],
                },
            ],
            "generated_from": str(day_path),
        },
    )

    settings = replace(
        build_settings(root),
        categorization_settings=replace(
            build_settings(root).categorization_settings,
            enabled=True,
        ),
    )
    categorizer = MockClusterCategorizer(
        categories_by_cluster_id={
            "cluster001": "architecture",
            "cluster002": "other",
        }
    )

    summary = run_cluster_categorization(settings, categorizer=categorizer)

    assert summary.categorized_days == 1
    assert summary.classified_clusters == 2
    assert summary.photos_moved == 3
    assert (day_path / "architecture" / "c001_b001_001.jpg").exists()
    assert (day_path / "architecture" / "c001_b002_001.jpg").exists()
    assert (day_path / "other" / "c002_b002_001.jpg").exists()
    assert (day_path / "rejected" / "ignore.jpg").exists()
    assert (day_path / "not_photo" / "also_ignore.jpg").exists()
    assert categorizer.calls == [
        ("day01", "cluster001", "c001_b001_001.jpg"),
        ("day01", "cluster002", "c002_b002_001.jpg"),
    ]

    payload = json.loads((day_path / "cluster_manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["category_counts"] == {"architecture": 2, "other": 1}
    assert payload["clusters"][0]["category_name"] == "architecture"
    assert payload["clusters"][0]["members"][0]["relative_path"] == "day01/architecture/c001_b001_001.jpg"
    assert payload["clusters"][0]["members"][1]["relative_path"] == "day01/architecture/c001_b002_001.jpg"
    assert payload["clusters"][1]["category_name"] == "other"
    assert payload["clusters"][1]["members"][0]["relative_path"] == "day01/other/c002_b002_001.jpg"


def _build_member(filename: str, burst_group_id: str, captured_at: str) -> dict:
    return {
        "filename": filename,
        "relative_path": str(Path("day01") / filename),
        "burst_group_id": burst_group_id,
        "captured_at": captured_at,
        "orientation": "landscape",
        "blur_score": 10.0,
        "brightness_mean": 100.0,
        "overexposed_ratio": 0.1,
        "cosine_distance_to_representative": 0.0,
        "histogram_similarity_to_representative": 1.0,
        "perceptual_hash_distance_to_representative": 0,
    }


def _write_cluster_manifest(day_path: Path, payload: dict) -> None:
    (day_path / "cluster_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
