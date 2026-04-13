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
    accepted_photos: int
    rejected_photos: int
    day_count: int
    moved_files: int
    created_directories: int
    clustered_days: int = 0
    burst_group_count: int = 0
    final_cluster_count: int = 0
    manifests_written: int = 0
    ranked_days: int = 0
    ranked_candidates: int = 0
    selected_photos: int = 0
    day_selection_manifests_written: int = 0
    trip_selection_manifest_written: bool = False

    def to_report(self) -> str:
        """Render a concise CLI report."""

        lines = [
            "Memory Picker run summary",
            f"  total_items: {self.total_items}",
            f"  photo_items: {self.photo_items}",
            f"  non_photo_items: {self.non_photo_items}",
            f"  unsupported_items: {self.unsupported_items}",
            f"  accepted_photos: {self.accepted_photos}",
            f"  rejected_photos: {self.rejected_photos}",
            f"  day_count: {self.day_count}",
            f"  moved_files: {self.moved_files}",
            f"  created_directories: {self.created_directories}",
            f"  clustered_days: {self.clustered_days}",
            f"  burst_group_count: {self.burst_group_count}",
            f"  final_cluster_count: {self.final_cluster_count}",
            f"  manifests_written: {self.manifests_written}",
            f"  ranked_days: {self.ranked_days}",
            f"  ranked_candidates: {self.ranked_candidates}",
            f"  selected_photos: {self.selected_photos}",
            f"  day_selection_manifests_written: {self.day_selection_manifests_written}",
            f"  trip_selection_manifest_written: {self.trip_selection_manifest_written}",
        ]
        return "\n".join(lines)


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
class DayCandidatePhoto:
    """A post-dedup day candidate that may be sent to GPT ranking."""

    photo_id: str
    day_name: str
    source_path: Path
    relative_path: Path
    cluster_id: str
    burst_group_id: str
    captured_at: datetime
    blur_score: float | None = None
    brightness_mean: float | None = None
    overexposed_ratio: float | None = None


@dataclass(frozen=True)
class DayRankingRecord:
    """Structured GPT ranking output for a single candidate photo."""

    photo_id: str
    rank: int
    overall_score: float
    technical_quality_score: float
    storytelling_score: float
    distinctiveness_score: float
    theme_tags: tuple[str, ...]
    rationale: str
    is_good_enough: bool
    normalized_score: float


@dataclass(frozen=True)
class DaySelectionManifest:
    """Persisted day ranking results for local reuse."""

    day_name: str
    manifest_path: Path
    candidate_count: int
    ranked_count: int
    good_enough_count: int
    provisional_selected_count: int = 0
    finalist_shortlist_count: int = 0
    final_selected_count: int = 0


@dataclass(frozen=True)
class DaySelectionResult:
    """In-memory representation of one day's Epic 3 ranking output."""

    day_name: str
    candidates: tuple[DayCandidatePhoto, ...]
    rankings: tuple[DayRankingRecord, ...]
    manifest_path: Path
    prompt_name: str
    model_name: str
    response_id: str | None = None
    provisional_photo_ids: tuple[str, ...] = ()
    finalist_photo_ids: tuple[str, ...] = ()
    selection_decisions: tuple["PhotoSelectionDecision", ...] = ()


@dataclass(frozen=True)
class DayRankingBatch:
    """Ranker output before the manifest is written."""

    day_name: str
    rankings: tuple[DayRankingRecord, ...]
    prompt_name: str
    model_name: str
    response_id: str | None = None


@dataclass(frozen=True)
class FinalistCandidate:
    """A second-pass finalist considered against other shortlisted photos."""

    day_name: str
    photo_id: str
    source_path: Path
    relative_path: Path
    cluster_id: str
    burst_group_id: str
    first_pass_rank: int
    normalized_score: float
    overall_score: float
    theme_tags: tuple[str, ...]
    rationale: str
    shortlist_origin: str
    provisional_selected: bool


@dataclass(frozen=True)
class FinalCurationRecord:
    """Structured second-pass curation output for one shortlisted finalist."""

    photo_id: str
    rank: int
    keep_for_album: bool
    duplicate_of_photo_id: str | None
    materially_distinct_exception: bool
    rationale: str


@dataclass(frozen=True)
class FinalCurationBatch:
    """Shortlist curation output before local cluster/day/trip rules are applied."""

    rankings: tuple[FinalCurationRecord, ...]
    prompt_name: str
    model_name: str
    response_id: str | None = None


@dataclass(frozen=True)
class PhotoSelectionDecision:
    """Local final-selection bookkeeping for one ranked photo."""

    day_name: str
    photo_id: str
    provisional_selected: bool = False
    finalist_shortlisted: bool = False
    shortlist_origin: str | None = None
    final_curation_status: str = "not_shortlisted"
    duplicate_of_photo_id: str | None = None
    used_cluster_exception: bool = False
    final_curation_rank: int | None = None


@dataclass(frozen=True)
class TripSelectedPhoto:
    """A final selected photo after trip-wide caps and spillover logic."""

    day_name: str
    photo_id: str
    source_path: Path
    relative_path: Path
    cluster_id: str
    burst_group_id: str
    rank: int
    normalized_score: float
    overall_score: float
    theme_tags: tuple[str, ...]
    rationale: str
    shortlist_origin: str
    provisional_selected: bool
    used_cluster_exception: bool = False
    final_curation_rank: int | None = None


@dataclass(frozen=True)
class TripSelectionManifest:
    """Persisted trip-wide selection result."""

    manifest_path: Path
    selected_count: int
    clusters_represented: int = 0
    duplicate_rejections: int = 0
    cluster_exceptions_used: int = 0
    unfilled_capacity_reason: str | None = None


@dataclass(frozen=True)
class SelectionRunSummary:
    """Epic 3 summary across all processed days."""

    ranked_days: int = 0
    ranked_candidates: int = 0
    selected_photos: int = 0
    day_manifests_written: int = 0
    trip_manifest_written: bool = False
