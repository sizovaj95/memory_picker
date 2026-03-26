"""Tests for Epic 2 manifest generation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from memory_picker.cluster_outputs import build_cluster_manifest_payload
from memory_picker.models import (
    AcceptedPhotoRecord,
    BurstGroup,
    DayCluster,
    DeterministicSimilarityFeatures,
    Orientation,
    QualityMetrics,
)
from tests.helpers import normalize_vector


def make_record(filename: str, blur_score: float) -> AcceptedPhotoRecord:
    source_path = Path("/tmp") / filename
    captured_at = datetime(2026, 1, 1, 10, 0, 0)
    return AcceptedPhotoRecord(
        day_name="day01",
        source_path=source_path,
        relative_path=Path("day01") / filename,
        captured_at=captured_at,
        captured_on=captured_at.date(),
        width=100,
        height=80,
        orientation=Orientation.LANDSCAPE,
        quality_metrics=QualityMetrics(
            blur_score=blur_score,
            brightness_mean=100.0,
            overexposed_ratio=0.1,
        ),
        similarity_features=DeterministicSimilarityFeatures(
            perceptual_hash=10,
            color_histogram=tuple([1.0 / 24.0] * 24),
        ),
    )


def test_build_cluster_manifest_payload_contains_summary_and_ordered_clusters():
    records = [make_record("a.jpg", 20.0), make_record("b.jpg", 30.0)]
    burst_groups = [
        BurstGroup(
            burst_group_id="burst001",
            day_name="day01",
            member_paths=(Path("/tmp/a.jpg"), Path("/tmp/b.jpg")),
            representative_path=Path("/tmp/b.jpg"),
        )
    ]
    day_clusters = [
        DayCluster(
            cluster_id="cluster001",
            day_name="day01",
            member_paths=(Path("/tmp/a.jpg"), Path("/tmp/b.jpg")),
            burst_group_ids=("burst001",),
            representative_path=Path("/tmp/b.jpg"),
        )
    ]
    embeddings_by_path = {
        Path("/tmp/a.jpg"): normalize_vector([1.0, 0.0]),
        Path("/tmp/b.jpg"): normalize_vector([0.9, 0.1]),
    }

    payload = build_cluster_manifest_payload(
        day_name="day01",
        day_path=Path("/trip/day01"),
        photo_records=records,
        burst_groups=burst_groups,
        day_clusters=day_clusters,
        embeddings_by_path=embeddings_by_path,
    )

    assert payload["summary"] == {
        "accepted_photo_count": 2,
        "burst_group_count": 1,
        "cluster_count": 1,
        "singleton_cluster_count": 0,
    }
    assert payload["clusters"][0]["cluster_id"] == "cluster001"
    assert payload["clusters"][0]["representative_filename"] == "b.jpg"
    assert payload["clusters"][0]["member_filenames"] == ["a.jpg", "b.jpg"]
