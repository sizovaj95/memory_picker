"""Tests for Epic 2 burst grouping and day clustering."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from memory_picker.clustering import build_burst_groups, build_day_clusters
from memory_picker.config import ClusteringThresholds
from memory_picker.models import (
    AcceptedPhotoRecord,
    DeterministicSimilarityFeatures,
    Orientation,
    QualityMetrics,
)
from tests.helpers import normalize_vector


def make_record(
    filename: str,
    captured_at: datetime,
    blur_score: float,
    perceptual_hash: int,
    histogram: tuple[float, ...],
) -> AcceptedPhotoRecord:
    path = Path("/tmp") / filename
    return AcceptedPhotoRecord(
        day_name="day01",
        source_path=path,
        relative_path=Path("day01") / filename,
        captured_at=captured_at,
        captured_on=captured_at.date(),
        width=120,
        height=80,
        orientation=Orientation.LANDSCAPE,
        quality_metrics=QualityMetrics(blur_score=blur_score),
        similarity_features=DeterministicSimilarityFeatures(
            perceptual_hash=perceptual_hash,
            color_histogram=histogram,
        ),
    )


def test_build_burst_groups_links_near_duplicates_and_picks_sharpest_representative():
    histogram = tuple([1.0 / 24.0] * 24)
    records = [
        make_record("a1.jpg", datetime(2026, 1, 1, 10, 0, 0), 20.0, 10, histogram),
        make_record("a2.jpg", datetime(2026, 1, 1, 10, 0, 20), 50.0, 11, histogram),
        make_record("b1.jpg", datetime(2026, 1, 1, 12, 0, 0), 35.0, 999, tuple([0.0] * 24)),
    ]

    burst_groups = build_burst_groups(records, ClusteringThresholds())

    assert len(burst_groups) == 2
    assert burst_groups[0].member_paths == (Path("/tmp/a1.jpg"), Path("/tmp/a2.jpg"))
    assert burst_groups[0].representative_path == Path("/tmp/a2.jpg")
    assert burst_groups[1].member_paths == (Path("/tmp/b1.jpg"),)


def test_build_day_clusters_uses_embeddings_and_selects_medoid():
    histogram = tuple([1.0 / 24.0] * 24)
    records = [
        make_record("a1.jpg", datetime(2026, 1, 1, 10, 0, 0), 30.0, 10, histogram),
        make_record("a2.jpg", datetime(2026, 1, 1, 10, 0, 15), 45.0, 10, histogram),
        make_record("b1.jpg", datetime(2026, 1, 1, 11, 0, 0), 40.0, 50, histogram),
        make_record("c1.jpg", datetime(2026, 1, 1, 14, 0, 0), 40.0, 500, tuple([0.0] * 24)),
    ]
    thresholds = ClusteringThresholds(
        burst_time_gap_seconds=120,
        perceptual_hash_hamming_threshold=1,
        histogram_similarity_threshold=0.9,
        semantic_cosine_distance_threshold=0.2,
    )
    burst_groups = build_burst_groups(records, thresholds)
    embeddings_by_path = {
        Path("/tmp/a1.jpg"): normalize_vector([1.0, 0.0, 0.0]),
        Path("/tmp/a2.jpg"): normalize_vector([0.98, 0.02, 0.0]),
        Path("/tmp/b1.jpg"): normalize_vector([0.96, 0.04, 0.0]),
        Path("/tmp/c1.jpg"): normalize_vector([0.0, 1.0, 0.0]),
    }

    day_clusters = build_day_clusters("day01", burst_groups, embeddings_by_path, thresholds)

    assert len(day_clusters) == 2
    assert day_clusters[0].member_paths == (
        Path("/tmp/a1.jpg"),
        Path("/tmp/a2.jpg"),
        Path("/tmp/b1.jpg"),
    )
    assert day_clusters[0].representative_path == Path("/tmp/a2.jpg")
    assert day_clusters[1].member_paths == (Path("/tmp/c1.jpg"),)
