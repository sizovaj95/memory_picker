"""Epic 2 orchestration for preprocessing and clustering."""

from __future__ import annotations

import logging

from memory_picker.cluster_outputs import write_day_cluster_manifest
from memory_picker.clustering import build_burst_groups, build_day_clusters
from memory_picker.config import AppSettings
from memory_picker.embeddings import DinoV2ImageEmbedder, ImageEmbedder
from memory_picker.models import ClusteringRunSummary
from memory_picker.preprocessing import iter_day_directories, load_day_photo_records

LOGGER = logging.getLogger("memory_picker.cluster_pipeline")


def build_default_embedder(settings: AppSettings) -> ImageEmbedder:
    """Build the default Epic 2 image embedder."""

    return DinoV2ImageEmbedder(settings.embedding_settings)


def run_clustering_pipeline(
    settings: AppSettings,
    embedder: ImageEmbedder | None = None,
) -> ClusteringRunSummary:
    """Cluster accepted photos for all existing day folders."""

    day_directories = iter_day_directories(settings)
    if not day_directories:
        return ClusteringRunSummary()

    LOGGER.info("Preparing accepted-photo records for %s day folders", len(day_directories))
    photo_records_by_day = {
        day_path.name: load_day_photo_records(day_path, settings) for day_path in day_directories
    }
    clustered_day_names = [day_name for day_name, records in photo_records_by_day.items() if records]
    if not clustered_day_names:
        return ClusteringRunSummary()

    active_embedder = embedder or build_default_embedder(settings)
    burst_group_count = 0
    cluster_count = 0
    manifests_written = 0
    accepted_photo_count = 0

    for day_path in day_directories:
        photo_records = photo_records_by_day[day_path.name]
        if not photo_records:
            continue

        LOGGER.info("Clustering %s with %s accepted photos", day_path.name, len(photo_records))
        accepted_photo_count += len(photo_records)
        embeddings = active_embedder.embed_images(photo_records)
        embeddings_by_path = {embedding.source_path: embedding.vector for embedding in embeddings}
        burst_groups = build_burst_groups(photo_records, settings.clustering_thresholds)
        day_clusters = build_day_clusters(
            day_name=day_path.name,
            burst_groups=burst_groups,
            embeddings_by_path=embeddings_by_path,
            thresholds=settings.clustering_thresholds,
        )
        write_day_cluster_manifest(
            day_path=day_path,
            day_name=day_path.name,
            photo_records=photo_records,
            burst_groups=burst_groups,
            day_clusters=day_clusters,
            embeddings_by_path=embeddings_by_path,
        )

        burst_group_count += len(burst_groups)
        cluster_count += len(day_clusters)
        manifests_written += 1
        LOGGER.info(
            "Clustered %s: accepted=%s burst_groups=%s clusters=%s",
            day_path.name,
            len(photo_records),
            len(burst_groups),
            len(day_clusters),
        )

    return ClusteringRunSummary(
        clustered_days=len(clustered_day_names),
        accepted_photo_count=accepted_photo_count,
        burst_group_count=burst_group_count,
        cluster_count=cluster_count,
        manifests_written=manifests_written,
    )
