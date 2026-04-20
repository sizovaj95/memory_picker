"""Mandatory front-of-pipeline HEIF/HEIC to JPEG conversion."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from memory_picker.config import AppSettings
from memory_picker.image_support import register_heif_support
from memory_picker.logging_utils import log_progress
from memory_picker.models import HeifConversionSummary

LOGGER = logging.getLogger("memory_picker.heif_conversion")

HEIF_EXTENSIONS = frozenset({"heic", "heif"})
JPEG_QUALITY = 95


def convert_trip_root_heif_files(settings: AppSettings) -> HeifConversionSummary:
    """Convert top-level HEIF/HEIC files into sibling JPEG files before intake."""

    candidates = [
        path
        for path in sorted(settings.root_path.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower().lstrip(".") in HEIF_EXTENSIONS
    ]
    if not candidates:
        LOGGER.info("Stage 0/7: no HEIF/HEIC files found for conversion")
        return HeifConversionSummary()

    LOGGER.info("Stage 0/7: converting %s HEIF/HEIC files to JPEG", len(candidates))
    converted_files = 0
    deleted_original_files = 0
    for index, source_path in enumerate(candidates, start=1):
        _convert_heif_file(source_path, settings)
        converted_files += 1
        deleted_original_files += 1
        log_progress(LOGGER, "Converting", index, len(candidates), noun="photo")

    LOGGER.info(
        "Completed stage 0/7: converted_heif_files=%s deleted_original_heif_files=%s",
        converted_files,
        deleted_original_files,
    )
    return HeifConversionSummary(
        converted_files=converted_files,
        deleted_original_files=deleted_original_files,
    )


def _convert_heif_file(source_path: Path, settings: AppSettings) -> Path:
    """Convert one HEIF/HEIC file into JPEG, preserving metadata and timestamps."""

    register_heif_support()
    target_path = _resolve_converted_target_path(source_path, settings)
    stat_result = source_path.stat()
    temp_path: Path | None = None

    try:
        with Image.open(source_path) as image:
            normalized = image.convert("RGB")
            exif = image.getexif()
            exif_bytes = exif.tobytes() if exif else None
            with NamedTemporaryFile(
                suffix=".jpg",
                prefix=f"{source_path.stem}_",
                dir=source_path.parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)

            save_kwargs = {"format": "JPEG", "quality": JPEG_QUALITY}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            normalized.save(temp_path, **save_kwargs)

        os.utime(temp_path, (stat_result.st_atime, stat_result.st_mtime))
        temp_path.replace(target_path)
        source_path.unlink()
        return target_path
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def _resolve_converted_target_path(source_path: Path, settings: AppSettings) -> Path:
    """Return a collision-safe JPEG target for a converted HEIF/HEIC file."""

    base_target = source_path.with_suffix(".jpg")
    if not base_target.exists():
        return base_target

    counter = 1
    while True:
        candidate = base_target.with_name(
            f"{base_target.stem}{settings.conversion_collision_suffix_separator}{counter:02d}"
            f"{base_target.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1
