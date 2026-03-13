"""Trip root scanning and initial file classification."""

from __future__ import annotations

import logging
from pathlib import Path

from memory_picker.config import AppSettings
from memory_picker.models import MediaClassification, MediaInventoryItem

LOGGER = logging.getLogger("memory_picker.inventory")


def classify_path(path: Path, settings: AppSettings) -> MediaClassification:
    """Classify a file using its extension only."""

    extension = path.suffix.lower().lstrip(".")
    if extension in settings.supported_photo_extensions:
        return MediaClassification.PHOTO
    if extension in settings.non_photo_extensions:
        return MediaClassification.NON_PHOTO
    return MediaClassification.UNSUPPORTED


def scan_trip_root(settings: AppSettings) -> list[MediaInventoryItem]:
    """Return a deterministic inventory of top-level files in the trip root."""

    if not settings.root_path.exists():
        raise FileNotFoundError(f"Trip root does not exist: {settings.root_path}")
    if not settings.root_path.is_dir():
        raise NotADirectoryError(f"Trip root is not a directory: {settings.root_path}")

    inventory: list[MediaInventoryItem] = []
    for path in sorted(settings.root_path.iterdir(), key=lambda item: item.name.lower()):
        if path.is_dir():
            if settings.is_managed_directory(path.name):
                LOGGER.debug("Skipping managed directory: %s", path)
            else:
                LOGGER.debug("Skipping nested directory in flat input mode: %s", path)
            continue

        stat = path.stat()
        inventory.append(
            MediaInventoryItem(
                source_path=path.resolve(),
                extension=path.suffix.lower().lstrip("."),
                size_bytes=stat.st_size,
                classification=classify_path(path, settings),
            )
        )

    return inventory
