"""Shared domain models for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

import numpy as np


class MediaClassification(StrEnum):
    """Initial file classification before image inspection."""

    PHOTO = "photo"
    NON_PHOTO = "non_photo"
    UNSUPPORTED = "unsupported"


class TimestampSource(StrEnum):
    """Timestamp provenance used for day assignment."""

    EXIF = "exif"
    MTIME = "mtime"


class RejectionReason(StrEnum):
    """Deterministic rejection reasons for local quality checks."""

    BLURRY = "blurry"
    CORRUPT = "corrupt"
    TOO_BRIGHT = "too_bright"
    TOO_DARK = "too_dark"


class DestinationCategory(StrEnum):
    """Destination bucket for moved files."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_PHOTO = "not_photo"


class Orientation(StrEnum):
    """Simple photo orientation classification."""

    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


@dataclass(frozen=True)
class MediaInventoryItem:
    """A file discovered in the trip root."""

    source_path: Path
    extension: str
    size_bytes: int
    classification: MediaClassification


@dataclass(frozen=True)
class PhotoRecord:
    """Normalized photo metadata used for downstream processing."""

    inventory_item: MediaInventoryItem
    captured_at: datetime
    captured_on: date
    timestamp_source: TimestampSource

    @property
    def source_path(self) -> Path:
        return self.inventory_item.source_path


@dataclass(frozen=True)
class DayAssignment:
    """A resolved trip-day placement for a file."""

    source_path: Path
    captured_on: date
    day_index: int
    day_name: str
    timestamp_source: TimestampSource


@dataclass(frozen=True)
class QualityMetrics:
    """Numeric metrics produced by local quality checks."""

    blur_score: float | None = None
    brightness_mean: float | None = None
    overexposed_ratio: float | None = None


@dataclass(frozen=True)
class QualityAssessment:
    """Final quality verdict for a photo."""

    source_path: Path
    is_accepted: bool
    rejection_reasons: tuple[RejectionReason, ...] = ()
    metrics: QualityMetrics = field(default_factory=QualityMetrics)
    details: str | None = None


@dataclass(frozen=True)
class FileMovePlan:
    """Planned move for a file once decisions are complete."""

    source_path: Path
    day_name: str
    destination_category: DestinationCategory
    destination_subfolder: str | None = None


@dataclass(frozen=True)
class FileActionSummary:
    """Filesystem mutation summary."""

    accepted_moved: int = 0
    rejected_moved: int = 0
    artifacts_moved: int = 0
    created_directories: int = 0
    moved_paths: tuple[Path, ...] = ()

    @property
    def total_moved(self) -> int:
        return self.accepted_moved + self.rejected_moved + self.artifacts_moved


@dataclass(frozen=True)
class RunSummary:
    """User-facing summary returned by the pipeline."""

    total_items: int
    photo_items: int
    non_photo_items: int
    unsupported_items: int
    converted_heif_files: int
    deleted_original_heif_files: int
    accepted_photos: int
    rejected_photos: int
    day_count: int
    moved_files: int
    created_directories: int
    clustered_days: int = 0
    burst_group_count: int = 0
    final_cluster_count: int = 0
    manifests_written: int = 0
    duplicate_photos_rejected: int = 0
    renamed_photos: int = 0
    cleanup_manifests_rewritten: int = 0
    categorized_days: int = 0
    classified_clusters: int = 0
    categorized_photos_moved: int = 0
    categorization_manifests_rewritten: int = 0

    def to_report(self) -> str:
        """Render a concise CLI report."""

        lines = [
            "Memory Picker run summary",
            f"  total_items: {self.total_items}",
            f"  photo_items: {self.photo_items}",
            f"  non_photo_items: {self.non_photo_items}",
            f"  unsupported_items: {self.unsupported_items}",
            f"  converted_heif_files: {self.converted_heif_files}",
            f"  deleted_original_heif_files: {self.deleted_original_heif_files}",
            f"  accepted_photos: {self.accepted_photos}",
            f"  rejected_photos: {self.rejected_photos}",
            f"  day_count: {self.day_count}",
            f"  moved_files: {self.moved_files}",
            f"  created_directories: {self.created_directories}",
            f"  clustered_days: {self.clustered_days}",
            f"  burst_group_count: {self.burst_group_count}",
            f"  final_cluster_count: {self.final_cluster_count}",
            f"  manifests_written: {self.manifests_written}",
            f"  duplicate_photos_rejected: {self.duplicate_photos_rejected}",
            f"  renamed_photos: {self.renamed_photos}",
            f"  cleanup_manifests_rewritten: {self.cleanup_manifests_rewritten}",
            f"  categorized_days: {self.categorized_days}",
            f"  classified_clusters: {self.classified_clusters}",
            f"  categorized_photos_moved: {self.categorized_photos_moved}",
            f"  categorization_manifests_rewritten: {self.categorization_manifests_rewritten}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class HeifConversionSummary:
    """Summary of front-of-pipeline HEIF/HEIC to JPEG conversion."""

    converted_files: int = 0
    deleted_original_files: int = 0


@dataclass(frozen=True)
class DeterministicSimilarityFeatures:
    """Local handcrafted features used before model embeddings."""

    perceptual_hash: int
    color_histogram: tuple[float, ...]


@dataclass(frozen=True)
class AcceptedPhotoRecord:
    """Accepted day photo plus preprocessing metadata for clustering."""

    day_name: str
    source_path: Path
    relative_path: Path
    captured_at: datetime
    captured_on: date
    width: int
    height: int
    orientation: Orientation
    quality_metrics: QualityMetrics
    similarity_features: DeterministicSimilarityFeatures

    @property
    def filename(self) -> str:
        return self.source_path.name


@dataclass(frozen=True)
class ImageEmbedding:
    """Embedding vector for a single accepted photo."""

    source_path: Path
    vector: np.ndarray


@dataclass(frozen=True)
class BurstGroup:
    """Stage 1 burst / near-duplicate group."""

    burst_group_id: str
    day_name: str
    member_paths: tuple[Path, ...]
    representative_path: Path


@dataclass(frozen=True)
class DayCluster:
    """Stage 2 final within-day cluster."""

    cluster_id: str
    day_name: str
    member_paths: tuple[Path, ...]
    burst_group_ids: tuple[str, ...]
    representative_path: Path


@dataclass(frozen=True)
class DayClusterManifest:
    """Written manifest summary for one day."""

    day_name: str
    manifest_path: Path
    accepted_photo_count: int
    burst_group_count: int
    cluster_count: int
    singleton_cluster_count: int


@dataclass(frozen=True)
class ClusteringRunSummary:
    """Epic 2 clustering summary across all day folders."""

    clustered_days: int = 0
    accepted_photo_count: int = 0
    burst_group_count: int = 0
    cluster_count: int = 0
    manifests_written: int = 0


@dataclass(frozen=True)
class CleanupRunSummary:
    """Epic 3 deterministic post-cluster cleanup summary."""

    processed_days: int = 0
    duplicate_photos_rejected: int = 0
    renamed_photos: int = 0
    manifests_rewritten: int = 0


@dataclass(frozen=True)
class ClusterCategorizationResult:
    """Classification result for one representative image."""

    category_name: str
    rationale: str
    model_name: str
    response_id: str | None = None


@dataclass(frozen=True)
class CategorizationRunSummary:
    """Epic 4 optional AI categorization summary."""

    categorized_days: int = 0
    classified_clusters: int = 0
    photos_moved: int = 0
    manifests_rewritten: int = 0
