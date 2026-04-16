"""Epic 2 deterministic burst grouping and semantic clustering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from memory_picker.config import ClusteringThresholds
from memory_picker.models import AcceptedPhotoRecord, BurstGroup, DayCluster


@dataclass
class _DisjointSet:
    parent: dict[int, int]

    @classmethod
    def create(cls, size: int) -> "_DisjointSet":
        return cls(parent={index: index for index in range(size)})

    def find(self, index: int) -> int:
        root = self.parent[index]
        if root != index:
            self.parent[index] = self.find(root)
        return self.parent[index]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def hamming_distance(left: int, right: int) -> int:
    """Return the Hamming distance between two 64-bit hashes."""

    return (left ^ right).bit_count()


def cosine_similarity(left: np.ndarray | tuple[float, ...], right: np.ndarray | tuple[float, ...]) -> float:
    """Return cosine similarity between two vectors."""

    left_array = np.asarray(left, dtype=np.float32)
    right_array = np.asarray(right, dtype=np.float32)
    denominator = np.linalg.norm(left_array) * np.linalg.norm(right_array)
    if denominator == 0:
        return 0.0
    return float(np.dot(left_array, right_array) / denominator)


def cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    """Return cosine distance between normalized vectors."""

    return float(1.0 - cosine_similarity(left, right))


def should_link_burst(
    left: AcceptedPhotoRecord,
    right: AcceptedPhotoRecord,
    thresholds: ClusteringThresholds,
) -> bool:
    """Return True when two photos belong in the same burst group."""

    time_gap = abs((left.captured_at - right.captured_at).total_seconds())
    if time_gap > thresholds.burst_time_gap_seconds:
        return False

    perceptual_distance = hamming_distance(
        left.similarity_features.perceptual_hash,
        right.similarity_features.perceptual_hash,
    )
    histogram_similarity = cosine_similarity(
        left.similarity_features.color_histogram,
        right.similarity_features.color_histogram,
    )
    return (
        perceptual_distance <= thresholds.perceptual_hash_hamming_threshold
        or histogram_similarity >= thresholds.histogram_similarity_threshold
    )


def choose_burst_representative(records: list[AcceptedPhotoRecord]) -> Path:
    """Choose the sharpest photo in a burst group."""

    return sorted(
        records,
        key=lambda record: (
            -(record.quality_metrics.blur_score or 0.0),
            record.captured_at,
            str(record.relative_path),
        ),
    )[0].source_path


def build_burst_groups(
    photo_records: list[AcceptedPhotoRecord],
    thresholds: ClusteringThresholds,
) -> list[BurstGroup]:
    """Build Stage 1 burst groups from deterministic signals."""

    if not photo_records:
        return []

    ordered_records = sorted(photo_records, key=lambda record: (record.captured_at, str(record.relative_path)))
    disjoint_set = _DisjointSet.create(len(ordered_records))

    for left_index, left_record in enumerate(ordered_records):
        for right_index in range(left_index + 1, len(ordered_records)):
            right_record = ordered_records[right_index]
            if not should_link_burst(left_record, right_record, thresholds):
                continue
            disjoint_set.union(left_index, right_index)

    grouped_records: dict[int, list[AcceptedPhotoRecord]] = {}
    for index, record in enumerate(ordered_records):
        root = disjoint_set.find(index)
        grouped_records.setdefault(root, []).append(record)

    burst_groups: list[BurstGroup] = []
    for burst_index, records in enumerate(
        sorted(grouped_records.values(), key=lambda group: (group[0].captured_at, str(group[0].relative_path))),
        start=1,
    ):
        burst_groups.append(
            BurstGroup(
                burst_group_id=f"burst{burst_index:03d}",
                day_name=records[0].day_name,
                member_paths=tuple(record.source_path for record in records),
                representative_path=choose_burst_representative(records),
            )
        )
    return burst_groups


def average_cluster_distance(
    left_cluster: list[Path],
    right_cluster: list[Path],
    embeddings_by_path: dict[Path, np.ndarray],
) -> float:
    """Return average pairwise distance between two clusters."""

    distances = [
        cosine_distance(embeddings_by_path[left], embeddings_by_path[right])
        for left in left_cluster
        for right in right_cluster
    ]
    return float(sum(distances) / len(distances))


def agglomerative_cluster_representatives(
    representative_paths: list[Path],
    embeddings_by_path: dict[Path, np.ndarray],
    thresholds: ClusteringThresholds,
) -> list[list[Path]]:
    """Cluster burst representatives using average-linkage cosine distance."""

    clusters = [[path] for path in representative_paths]
    if len(clusters) <= 1:
        return clusters

    while True:
        best_pair: tuple[int, int] | None = None
        best_distance: float | None = None

        for left_index in range(len(clusters)):
            for right_index in range(left_index + 1, len(clusters)):
                distance = average_cluster_distance(
                    clusters[left_index],
                    clusters[right_index],
                    embeddings_by_path,
                )
                if best_distance is None or distance < best_distance:
                    best_pair = (left_index, right_index)
                    best_distance = distance

        if best_pair is None or best_distance is None:
            break
        if best_distance > thresholds.semantic_cosine_distance_threshold:
            break

        left_index, right_index = best_pair
        merged_cluster = sorted(
            clusters[left_index] + clusters[right_index],
            key=lambda path: str(path),
        )
        clusters[left_index] = merged_cluster
        clusters.pop(right_index)

    return clusters


def choose_cluster_medoid(member_paths: list[Path], embeddings_by_path: dict[Path, np.ndarray]) -> Path:
    """Choose the medoid of a final cluster from full-photo embeddings."""

    if len(member_paths) == 1:
        return member_paths[0]

    scored_members: list[tuple[float, str, Path]] = []
    for candidate in member_paths:
        average_distance = sum(
            cosine_distance(embeddings_by_path[candidate], embeddings_by_path[other])
            for other in member_paths
        ) / len(member_paths)
        scored_members.append((average_distance, str(candidate), candidate))
    return min(scored_members)[2]


def build_day_clusters(
    day_name: str,
    burst_groups: list[BurstGroup],
    embeddings_by_path: dict[Path, np.ndarray],
    thresholds: ClusteringThresholds,
) -> list[DayCluster]:
    """Build final Stage 2 day clusters from burst representatives."""

    if not burst_groups:
        return []

    representative_paths = [group.representative_path for group in burst_groups]
    representative_clusters = agglomerative_cluster_representatives(
        representative_paths,
        embeddings_by_path,
        thresholds,
    )

    burst_by_representative = {group.representative_path: group for group in burst_groups}
    day_clusters: list[DayCluster] = []
    for cluster_index, representative_cluster in enumerate(representative_clusters, start=1):
        burst_groups_in_cluster = [burst_by_representative[path] for path in representative_cluster]
        member_paths = sorted(
            [path for group in burst_groups_in_cluster for path in group.member_paths],
            key=lambda path: str(path),
        )
        representative_path = choose_cluster_medoid(member_paths, embeddings_by_path)
        day_clusters.append(
            DayCluster(
                cluster_id=f"cluster{cluster_index:03d}",
                day_name=day_name,
                member_paths=tuple(member_paths),
                burst_group_ids=tuple(group.burst_group_id for group in burst_groups_in_cluster),
                representative_path=representative_path,
            )
        )

    return day_clusters
