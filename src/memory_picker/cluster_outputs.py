"""Epic 2 manifest generation and persistence."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from memory_picker.clustering import cosine_distance, cosine_similarity, hamming_distance
from memory_picker.models import (
    AcceptedPhotoRecord,
    BurstGroup,
    DayCluster,
    DayClusterManifest,
)


def build_cluster_manifest_payload(
    day_name: str,
    day_path: Path,
    photo_records: list[AcceptedPhotoRecord],
    burst_groups: list[BurstGroup],
    day_clusters: list[DayCluster],
    embeddings_by_path: dict[Path, np.ndarray],
) -> dict:
    """Build the JSON-serializable manifest payload for one day."""

    records_by_path = {record.source_path: record for record in photo_records}
    burst_group_id_by_member_path = {
        member_path: group.burst_group_id
        for group in burst_groups
        for member_path in group.member_paths
    }

    clusters_payload: list[dict] = []
    singleton_cluster_count = 0
    for cluster in day_clusters:
        if len(cluster.member_paths) == 1:
            singleton_cluster_count += 1

        representative_record = records_by_path[cluster.representative_path]
        representative_embedding = embeddings_by_path[cluster.representative_path]
        members_payload: list[dict] = []
        for member_path in sorted(cluster.member_paths, key=lambda path: str(path)):
            record = records_by_path[member_path]
            burst_group_id = burst_group_id_by_member_path[member_path]
            members_payload.append(
                {
                    "filename": record.filename,
                    "relative_path": str(record.relative_path),
                    "burst_group_id": burst_group_id,
                    "captured_at": record.captured_at.isoformat(),
                    "orientation": record.orientation.value,
                    "blur_score": record.quality_metrics.blur_score,
                    "brightness_mean": record.quality_metrics.brightness_mean,
                    "overexposed_ratio": record.quality_metrics.overexposed_ratio,
                    "cosine_distance_to_representative": cosine_distance(
                        embeddings_by_path[member_path],
                        representative_embedding,
                    ),
                    "histogram_similarity_to_representative": cosine_similarity(
                        record.similarity_features.color_histogram,
                        representative_record.similarity_features.color_histogram,
                    ),
                    "perceptual_hash_distance_to_representative": hamming_distance(
                        record.similarity_features.perceptual_hash,
                        representative_record.similarity_features.perceptual_hash,
                    ),
                }
            )

        clusters_payload.append(
            {
                "cluster_id": cluster.cluster_id,
                "representative_filename": representative_record.filename,
                "member_filenames": [records_by_path[path].filename for path in cluster.member_paths],
                "burst_group_ids": list(cluster.burst_group_ids),
                "member_count": len(cluster.member_paths),
                "members": members_payload,
            }
        )

    burst_groups_payload = [
        {
            "burst_group_id": group.burst_group_id,
            "representative_filename": records_by_path[group.representative_path].filename,
            "member_filenames": [records_by_path[path].filename for path in group.member_paths],
            "member_count": len(group.member_paths),
        }
        for group in burst_groups
    ]

    return {
        "day_name": day_name,
        "manifest_version": 1,
        "summary": {
            "accepted_photo_count": len(photo_records),
            "burst_group_count": len(burst_groups),
            "cluster_count": len(day_clusters),
            "singleton_cluster_count": singleton_cluster_count,
        },
        "burst_groups": burst_groups_payload,
        "clusters": clusters_payload,
        "generated_from": str(day_path),
    }


def write_day_cluster_manifest(
    day_path: Path,
    day_name: str,
    photo_records: list[AcceptedPhotoRecord],
    burst_groups: list[BurstGroup],
    day_clusters: list[DayCluster],
    embeddings_by_path: dict[Path, np.ndarray],
) -> DayClusterManifest:
    """Write one cluster manifest file next to the day photos."""

    manifest_path = day_path / "cluster_manifest.json"
    payload = build_cluster_manifest_payload(
        day_name=day_name,
        day_path=day_path,
        photo_records=photo_records,
        burst_groups=burst_groups,
        day_clusters=day_clusters,
        embeddings_by_path=embeddings_by_path,
    )
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return DayClusterManifest(
        day_name=day_name,
        manifest_path=manifest_path,
        accepted_photo_count=len(photo_records),
        burst_group_count=len(burst_groups),
        cluster_count=len(day_clusters),
        singleton_cluster_count=sum(1 for cluster in day_clusters if len(cluster.member_paths) == 1),
    )
