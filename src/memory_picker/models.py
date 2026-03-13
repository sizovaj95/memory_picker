"""Shared domain models for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path


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
        ]
        return "\n".join(lines)
