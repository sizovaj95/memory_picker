"""Tests for Epic 4 optional burst-group categorization."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import memory_picker.categorization as categorization_module
from memory_picker.categorization import (
    build_category_prompt,
    build_category_schema,
    run_cluster_categorization,
)
from memory_picker.config import build_settings
from memory_picker.models import ClusterCategorizationResult
from tests.helpers import MockClusterCategorizer, write_checkerboard_image


class TransientCategorizationError(RuntimeError):
    """Test-only retryable categorization failure."""


class FlakyAsyncCategorizer:
    """Async test categorizer that fails a fixed number of times before succeeding."""

    def __init__(self, failures_by_candidate_id: dict[tuple[str, str], int], categories_by_candidate_id: dict[tuple[str, str], str]) -> None:
        self.failures_by_candidate_id = failures_by_candidate_id
        self.categories_by_candidate_id = categories_by_candidate_id
        self.calls: list[tuple[str, str, str, str]] = []
        self.attempts_by_candidate_id: dict[tuple[str, str], int] = {}

    async def acategorize_cluster(
        self,
        day_name,
        cluster,
        burst_group_id,
        image_path,
        categorization_settings,
    ) -> ClusterCategorizationResult:
        self.calls.append((day_name, cluster["cluster_id"], burst_group_id, image_path.name))
        cluster_id = cluster["cluster_id"]
        candidate_id = (cluster_id, burst_group_id)
        attempt = self.attempts_by_candidate_id.get(candidate_id, 0) + 1
        self.attempts_by_candidate_id[candidate_id] = attempt
        if attempt <= self.failures_by_candidate_id.get(candidate_id, 0):
            raise TransientCategorizationError(f"retryable failure for {cluster_id}/{burst_group_id}")
        return ClusterCategorizationResult(
            category_name=self.categories_by_candidate_id[candidate_id],
            rationale=f"Recovered on attempt {attempt}",
            model_name="flaky-mock",
            response_id=f"mock-{cluster_id}-{burst_group_id}-{attempt}",
        )


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


def test_run_cluster_categorization_sends_one_representative_per_burst_group(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)
    write_checkerboard_image(day_path / "c001_b001_001.jpg")
    write_checkerboard_image(day_path / "c001_b001_002.jpg")
    write_checkerboard_image(day_path / "c001_b002_001.jpg")
    write_checkerboard_image(day_path / "c001_b002_002.jpg")
    write_checkerboard_image(day_path / "c001_b003_001.jpg")
    _write_cluster_manifest(
        day_path,
        {
            "day_name": "day01",
            "manifest_version": 1,
            "summary": {
                "accepted_photo_count": 5,
                "burst_group_count": 3,
                "cluster_count": 1,
                "singleton_cluster_count": 0,
            },
            "burst_groups": [
                {
                    "burst_group_id": "burst001",
                    "representative_filename": "c001_b001_001.jpg",
                    "member_filenames": ["c001_b001_001.jpg", "c001_b001_002.jpg"],
                    "member_count": 2,
                },
                {
                    "burst_group_id": "burst002",
                    "representative_filename": "c001_b002_001.jpg",
                    "member_filenames": ["c001_b002_001.jpg", "c001_b002_002.jpg"],
                    "member_count": 2,
                },
                {
                    "burst_group_id": "burst003",
                    "representative_filename": "c001_b003_001.jpg",
                    "member_filenames": ["c001_b003_001.jpg"],
                    "member_count": 1,
                },
            ],
            "clusters": [
                {
                    "cluster_id": "cluster001",
                    "representative_filename": "c001_b001_001.jpg",
                    "member_filenames": [
                        "c001_b001_001.jpg",
                        "c001_b001_002.jpg",
                        "c001_b002_001.jpg",
                        "c001_b002_002.jpg",
                        "c001_b003_001.jpg",
                    ],
                    "burst_group_ids": ["burst001", "burst002", "burst003"],
                    "member_count": 5,
                    "members": [
                        _build_member("c001_b001_001.jpg", "burst001", "2026-01-01T10:00:00"),
                        _build_member("c001_b001_002.jpg", "burst001", "2026-01-01T10:00:01"),
                        _build_member("c001_b002_001.jpg", "burst002", "2026-01-01T10:01:00"),
                        _build_member("c001_b002_002.jpg", "burst002", "2026-01-01T10:01:01"),
                        _build_member("c001_b003_001.jpg", "burst003", "2026-01-01T10:02:00"),
                    ],
                },
            ],
            "generated_from": str(day_path),
        },
    )
    settings = replace(
        build_settings(root),
        categorization_settings=replace(build_settings(root).categorization_settings, enabled=True),
    )
    categorizer = MockClusterCategorizer(
        categories_by_cluster_id={"cluster001": "architecture"},
        categories_by_burst_group={
            ("cluster001", "burst001"): "people",
            ("cluster001", "burst002"): "architecture",
            ("cluster001", "burst003"): "food",
        },
    )

    summary = run_cluster_categorization(settings, categorizer=categorizer)

    assert summary.classified_clusters == 1
    assert summary.photos_moved == 5
    assert categorizer.calls == [
        ("day01", "cluster001", "burst001", "c001_b001_001.jpg"),
        ("day01", "cluster001", "burst002", "c001_b002_001.jpg"),
        ("day01", "cluster001", "burst003", "c001_b003_001.jpg"),
    ]
    assert (day_path / "people" / "c001_b001_001.jpg").exists()
    assert (day_path / "people" / "c001_b001_002.jpg").exists()
    assert (day_path / "architecture" / "c001_b002_001.jpg").exists()
    assert (day_path / "architecture" / "c001_b002_002.jpg").exists()
    assert (day_path / "food" / "c001_b003_001.jpg").exists()

    payload = json.loads((day_path / "cluster_manifest.json").read_text(encoding="utf-8"))
    assert payload["manifest_version"] == 3
    assert payload["summary"]["categorized_cluster_count"] == 1
    assert payload["summary"]["categorized_burst_group_count"] == 3
    assert payload["summary"]["category_counts"] == {"people": 2, "architecture": 2, "food": 1}
    assert payload["clusters"][0]["burst_group_categories"] == [
        {
            "burst_group_id": "burst001",
            "category_name": "people",
            "classification_rationale": "Mock rationale for cluster001/burst001",
            "classification_source_filename": "c001_b001_001.jpg",
            "classification_model_name": "mock-categorizer",
            "classification_response_id": "mock-cluster001-burst001",
        },
        {
            "burst_group_id": "burst002",
            "category_name": "architecture",
            "classification_rationale": "Mock rationale for cluster001/burst002",
            "classification_source_filename": "c001_b002_001.jpg",
            "classification_model_name": "mock-categorizer",
            "classification_response_id": "mock-cluster001-burst002",
        },
        {
            "burst_group_id": "burst003",
            "category_name": "food",
            "classification_rationale": "Mock rationale for cluster001/burst003",
            "classification_source_filename": "c001_b003_001.jpg",
            "classification_model_name": "mock-categorizer",
            "classification_response_id": "mock-cluster001-burst003",
        },
    ]
    assert [member["category_name"] for member in payload["clusters"][0]["members"]] == [
        "people",
        "people",
        "architecture",
        "architecture",
        "food",
    ]


def test_run_cluster_categorization_moves_accepted_photos_and_rewrites_manifest(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    (day_path / "_rejected" / "low_quality").mkdir(parents=True)
    (day_path / "_rejected" / "not_photo").mkdir(parents=True)
    write_checkerboard_image(day_path / "c001_b001_001.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 0))
    write_checkerboard_image(day_path / "c001_b002_001.jpg", capture_datetime=datetime(2026, 1, 1, 10, 1, 0))
    write_checkerboard_image(day_path / "c002_b002_001.jpg", capture_datetime=datetime(2026, 1, 1, 11, 0, 0))
    write_checkerboard_image(day_path / "_rejected" / "low_quality" / "ignore.jpg")
    write_checkerboard_image(day_path / "_rejected" / "not_photo" / "also_ignore.jpg")
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
        },
        categories_by_burst_group={
            ("cluster001", "burst001"): "architecture",
            ("cluster001", "burst002"): "people",
            ("cluster002", "burst003"): "other",
        }
    )

    summary = run_cluster_categorization(settings, categorizer=categorizer)

    assert summary.categorized_days == 1
    assert summary.classified_clusters == 2
    assert summary.photos_moved == 3
    assert (day_path / "architecture" / "c001_b001_001.jpg").exists()
    assert (day_path / "people" / "c001_b002_001.jpg").exists()
    assert (day_path / "other" / "c002_b002_001.jpg").exists()
    assert (day_path / "_rejected" / "low_quality" / "ignore.jpg").exists()
    assert (day_path / "_rejected" / "not_photo" / "also_ignore.jpg").exists()
    assert categorizer.calls == [
        ("day01", "cluster001", "burst001", "c001_b001_001.jpg"),
        ("day01", "cluster001", "burst002", "c001_b002_001.jpg"),
        ("day01", "cluster002", "burst003", "c002_b002_001.jpg"),
    ]

    payload = json.loads((day_path / "cluster_manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["category_counts"] == {"architecture": 1, "people": 1, "other": 1}
    assert payload["summary"]["categorized_burst_group_count"] == 3
    assert payload["clusters"][0]["burst_group_categories"][0]["category_name"] == "architecture"
    assert payload["clusters"][0]["burst_group_categories"][1]["category_name"] == "people"
    assert payload["clusters"][0]["members"][0]["relative_path"] == "day01/architecture/c001_b001_001.jpg"
    assert payload["clusters"][0]["members"][0]["category_name"] == "architecture"
    assert payload["clusters"][0]["members"][1]["relative_path"] == "day01/people/c001_b002_001.jpg"
    assert payload["clusters"][0]["members"][1]["category_name"] == "people"
    assert payload["clusters"][1]["burst_group_categories"][0]["category_name"] == "other"
    assert payload["clusters"][1]["members"][0]["relative_path"] == "day01/other/c002_b002_001.jpg"


def test_run_cluster_categorization_retries_transient_failures_and_succeeds(tmp_path, monkeypatch):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)
    write_checkerboard_image(day_path / "c001_b001_001.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 0))
    _write_cluster_manifest(
        day_path,
        {
            "day_name": "day01",
            "manifest_version": 1,
            "summary": {
                "accepted_photo_count": 1,
                "burst_group_count": 1,
                "cluster_count": 1,
                "singleton_cluster_count": 1,
            },
            "burst_groups": [
                {
                    "burst_group_id": "burst001",
                    "representative_filename": "c001_b001_001.jpg",
                    "member_filenames": ["c001_b001_001.jpg"],
                    "member_count": 1,
                }
            ],
            "clusters": [
                {
                    "cluster_id": "cluster001",
                    "representative_filename": "c001_b001_001.jpg",
                    "member_filenames": ["c001_b001_001.jpg"],
                    "burst_group_ids": ["burst001"],
                    "member_count": 1,
                    "members": [
                        _build_member("c001_b001_001.jpg", "burst001", "2026-01-01T10:00:00"),
                    ],
                }
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
        categorization_concurrency_settings=replace(
            build_settings(root).categorization_concurrency_settings,
            max_retries=2,
            initial_retry_delay_seconds=0.001,
        ),
    )
    categorizer = FlakyAsyncCategorizer(
        failures_by_candidate_id={("cluster001", "burst001"): 2},
        categories_by_candidate_id={("cluster001", "burst001"): "architecture"},
    )
    monkeypatch.setattr(
        categorization_module,
        "_is_retryable_categorization_error",
        lambda exc: isinstance(exc, TransientCategorizationError),
    )

    summary = run_cluster_categorization(settings, categorizer=categorizer)

    assert summary.classified_clusters == 1
    assert categorizer.attempts_by_candidate_id == {("cluster001", "burst001"): 3}
    assert (day_path / "architecture" / "c001_b001_001.jpg").exists()


def test_run_cluster_categorization_does_not_partially_mutate_day_on_failed_retries(tmp_path, monkeypatch):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)
    write_checkerboard_image(day_path / "c001_b001_001.jpg", capture_datetime=datetime(2026, 1, 1, 10, 0, 0))
    write_checkerboard_image(day_path / "c002_b002_001.jpg", capture_datetime=datetime(2026, 1, 1, 11, 0, 0))
    payload = {
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
                "representative_filename": "c001_b001_001.jpg",
                "member_filenames": ["c001_b001_001.jpg"],
                "member_count": 1,
            },
            {
                "burst_group_id": "burst002",
                "representative_filename": "c002_b002_001.jpg",
                "member_filenames": ["c002_b002_001.jpg"],
                "member_count": 1,
            },
        ],
        "clusters": [
            {
                "cluster_id": "cluster001",
                "representative_filename": "c001_b001_001.jpg",
                "member_filenames": ["c001_b001_001.jpg"],
                "burst_group_ids": ["burst001"],
                "member_count": 1,
                "members": [
                    _build_member("c001_b001_001.jpg", "burst001", "2026-01-01T10:00:00"),
                ],
            },
            {
                "cluster_id": "cluster002",
                "representative_filename": "c002_b002_001.jpg",
                "member_filenames": ["c002_b002_001.jpg"],
                "burst_group_ids": ["burst002"],
                "member_count": 1,
                "members": [
                    _build_member("c002_b002_001.jpg", "burst002", "2026-01-01T11:00:00"),
                ],
            },
        ],
        "generated_from": str(day_path),
    }
    _write_cluster_manifest(day_path, payload)
    original_manifest = (day_path / "cluster_manifest.json").read_text(encoding="utf-8")

    settings = replace(
        build_settings(root),
        categorization_settings=replace(
            build_settings(root).categorization_settings,
            enabled=True,
        ),
        categorization_concurrency_settings=replace(
            build_settings(root).categorization_concurrency_settings,
            max_retries=1,
            initial_retry_delay_seconds=0.001,
            max_concurrent_requests=2,
        ),
    )
    categorizer = FlakyAsyncCategorizer(
        failures_by_candidate_id={("cluster002", "burst002"): 5},
        categories_by_candidate_id={
            ("cluster001", "burst001"): "architecture",
            ("cluster002", "burst002"): "other",
        },
    )
    monkeypatch.setattr(
        categorization_module,
        "_is_retryable_categorization_error",
        lambda exc: isinstance(exc, TransientCategorizationError),
    )

    try:
        run_cluster_categorization(settings, categorizer=categorizer)
    except TransientCategorizationError:
        pass
    else:
        raise AssertionError("Expected categorization to fail after retries were exhausted")

    assert (day_path / "c001_b001_001.jpg").exists()
    assert (day_path / "c002_b002_001.jpg").exists()
    assert not (day_path / "architecture").exists()
    assert (day_path / "cluster_manifest.json").read_text(encoding="utf-8") == original_manifest


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
