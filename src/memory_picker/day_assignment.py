"""Resolve capture dates and stable trip-day names."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PIL import ExifTags, Image, UnidentifiedImageError

from memory_picker.config import AppSettings
from memory_picker.image_support import register_heif_support
from memory_picker.models import DayAssignment, MediaInventoryItem, PhotoRecord, TimestampSource

EXIF_DATE_FIELDS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")
TAG_NAME_TO_ID = {tag_name: tag_id for tag_id, tag_name in ExifTags.TAGS.items()}


def parse_exif_datetime(value: str) -> datetime | None:
    """Parse a standard EXIF datetime string."""

    try:
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def extract_capture_datetime(path: Path) -> datetime | None:
    """Read the best available EXIF datetime from an image."""

    register_heif_support()
    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError):
        return None

    if not exif:
        return None

    for tag_name in EXIF_DATE_FIELDS:
        tag_id = TAG_NAME_TO_ID.get(tag_name)
        if tag_id is None:
            continue
        raw_value = exif.get(tag_id)
        if isinstance(raw_value, str):
            parsed = parse_exif_datetime(raw_value)
            if parsed is not None:
                return parsed

    return None


def infer_filesystem_datetime(path: Path) -> datetime:
    """Use the local filesystem modification time as a fallback timestamp."""

    return datetime.fromtimestamp(path.stat().st_mtime)


def resolve_photo_record(item: MediaInventoryItem) -> PhotoRecord:
    """Convert a photo inventory item into a timestamped photo record."""

    captured_at = extract_capture_datetime(item.source_path)
    timestamp_source = TimestampSource.EXIF

    if captured_at is None:
        captured_at = infer_filesystem_datetime(item.source_path)
        timestamp_source = TimestampSource.MTIME

    return PhotoRecord(
        inventory_item=item,
        captured_at=captured_at,
        captured_on=captured_at.date(),
        timestamp_source=timestamp_source,
    )


def build_day_map(captured_dates: list[date], settings: AppSettings) -> dict[date, str]:
    """Return a stable mapping from calendar date to dayXX name."""

    ordered_dates = sorted(set(captured_dates))
    return {
        captured_date: f"{settings.day_prefix}{index:02d}"
        for index, captured_date in enumerate(ordered_dates, start=1)
    }


def assign_day(
    source_path: Path,
    captured_on: date,
    timestamp_source: TimestampSource,
    day_map: dict[date, str],
) -> DayAssignment:
    """Resolve a single day assignment from an existing day map."""

    day_name = day_map[captured_on]
    return DayAssignment(
        source_path=source_path,
        captured_on=captured_on,
        day_index=int(day_name.removeprefix("day")),
        day_name=day_name,
        timestamp_source=timestamp_source,
    )


def build_day_assignments(
    photo_records: list[PhotoRecord],
    day_map: dict[date, str],
) -> list[DayAssignment]:
    """Assign all photo records to stable trip days."""

    return [
        assign_day(
            source_path=record.source_path,
            captured_on=record.captured_on,
            timestamp_source=record.timestamp_source,
            day_map=day_map,
        )
        for record in photo_records
    ]
