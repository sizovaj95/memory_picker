"""Epic 2 metadata extraction for accepted day photos."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from memory_picker.config import AppSettings, DAY_FOLDER_PATTERN
from memory_picker.day_assignment import extract_capture_datetime, infer_filesystem_datetime
from memory_picker.image_support import register_heif_support
from memory_picker.models import (
    AcceptedPhotoRecord,
    DeterministicSimilarityFeatures,
    Orientation,
    TimestampSource,
)
from memory_picker.quality import assess_photo


def iter_day_directories(settings: AppSettings) -> list[Path]:
    """Return existing dayXX directories in sorted order."""

    return sorted(
        [
            path
            for path in settings.root_path.iterdir()
            if path.is_dir() and DAY_FOLDER_PATTERN.fullmatch(path.name)
        ],
        key=lambda path: path.name,
    )


def classify_orientation(width: int, height: int) -> Orientation:
    """Return a simple orientation label from image dimensions."""

    if width > height:
        return Orientation.LANDSCAPE
    if height > width:
        return Orientation.PORTRAIT
    return Orientation.SQUARE


def compute_perceptual_hash(grayscale: np.ndarray) -> int:
    """Compute a simple 64-bit difference hash."""

    image = Image.fromarray(grayscale.astype(np.uint8), mode="L").resize((9, 8))
    resized = np.asarray(image, dtype=np.uint8)
    bits = resized[:, 1:] > resized[:, :-1]

    hash_value = 0
    for bit in bits.flatten():
        hash_value = (hash_value << 1) | int(bit)
    return hash_value


def compute_color_histogram(rgb_image: np.ndarray, bins_per_channel: int = 8) -> tuple[float, ...]:
    """Compute a normalized RGB histogram descriptor."""

    histograms: list[np.ndarray] = []
    for channel_index in range(3):
        histogram, _ = np.histogram(
            rgb_image[:, :, channel_index],
            bins=bins_per_channel,
            range=(0, 256),
        )
        histograms.append(histogram.astype(np.float32))

    combined = np.concatenate(histograms)
    total = combined.sum()
    if total == 0:
        return tuple(float(value) for value in combined)
    normalized = combined / total
    return tuple(float(value) for value in normalized)


def resolve_capture_datetime(path: Path) -> tuple[datetime, TimestampSource]:
    """Resolve the best available capture datetime for a clustered photo."""

    captured_at = extract_capture_datetime(path)
    if captured_at is not None:
        return captured_at, TimestampSource.EXIF
    return infer_filesystem_datetime(path), TimestampSource.MTIME


def build_accepted_photo_record(day_path: Path, photo_path: Path, settings: AppSettings) -> AcceptedPhotoRecord:
    """Create an enriched clustering record for one accepted photo."""

    register_heif_support()
    with Image.open(photo_path) as image:
        rgb_image = np.asarray(image.convert("RGB"), dtype=np.uint8)
        grayscale = np.asarray(image.convert("L"), dtype=np.uint8)
        width, height = image.size

    captured_at, _timestamp_source = resolve_capture_datetime(photo_path)
    quality_metrics = assess_photo(photo_path, settings.quality_thresholds).metrics

    return AcceptedPhotoRecord(
        day_name=day_path.name,
        source_path=photo_path.resolve(),
        relative_path=photo_path.resolve().relative_to(settings.root_path),
        captured_at=captured_at,
        captured_on=captured_at.date(),
        width=width,
        height=height,
        orientation=classify_orientation(width, height),
        quality_metrics=quality_metrics,
        similarity_features=DeterministicSimilarityFeatures(
            perceptual_hash=compute_perceptual_hash(grayscale),
            color_histogram=compute_color_histogram(rgb_image),
        ),
    )


def load_day_photo_records(day_path: Path, settings: AppSettings) -> list[AcceptedPhotoRecord]:
    """Load accepted photo records recursively, excluding rejected and not_photo."""

    records: list[AcceptedPhotoRecord] = []
    skipped_directory_names = {
        settings.managed_folders.rejected,
        settings.managed_folders.not_photo,
    }
    candidate_paths = sorted(
        [
            path
            for path in day_path.rglob("*")
            if path.is_file()
            and not any(part in skipped_directory_names for part in path.relative_to(day_path).parts[:-1])
        ],
        key=lambda item: str(item.relative_to(day_path)).lower(),
    )
    for path in candidate_paths:
        if path.name == "cluster_manifest.json":
            continue
        extension = path.suffix.lower().lstrip(".")
        if extension not in settings.supported_photo_extensions:
            continue
        records.append(build_accepted_photo_record(day_path, path, settings))
    return records
