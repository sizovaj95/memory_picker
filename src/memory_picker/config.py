"""Application configuration and defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DAY_FOLDER_PATTERN = re.compile(r"^day\d{2}$")

DEFAULT_SUPPORTED_PHOTO_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "heic"})
DEFAULT_NON_PHOTO_EXTENSIONS = frozenset(
    {
        "aae",
        "avi",
        "json",
        "m4v",
        "mov",
        "mp4",
        "txt",
        "wav",
        "xml",
    }
)


@dataclass(frozen=True)
class ManagedFolderNames:
    """Folder names reserved by the tool."""

    to_print: str = "to_print"
    rejected: str = "rejected"
    not_photo: str = "not_photo"


@dataclass(frozen=True)
class QualityThresholds:
    """Configurable local quality thresholds."""

    blur_threshold: float = 30.0
    blur_tile_rows: int = 6
    blur_tile_cols: int = 6
    blur_top_tile_fraction: float = 0.25
    dark_brightness_threshold: float = 40.0
    overexposed_pixel_threshold: float = 250.0
    overexposed_ratio_threshold: float = 0.60


@dataclass(frozen=True)
class AppSettings:
    """Settings used by the local pipeline."""

    root_path: Path
    supported_photo_extensions: frozenset[str] = field(
        default_factory=lambda: DEFAULT_SUPPORTED_PHOTO_EXTENSIONS
    )
    non_photo_extensions: frozenset[str] = field(
        default_factory=lambda: DEFAULT_NON_PHOTO_EXTENSIONS
    )
    managed_folders: ManagedFolderNames = field(default_factory=ManagedFolderNames)
    quality_thresholds: QualityThresholds = field(default_factory=QualityThresholds)
    day_prefix: str = "day"
    collision_suffix_separator: str = "__dup"
    max_photos_per_day: int | None = None
    max_photos_total: int | None = None

    def is_managed_directory(self, name: str) -> bool:
        """Return True when the directory is owned by the tool."""

        return name in {
            self.managed_folders.to_print,
            self.managed_folders.rejected,
            self.managed_folders.not_photo,
        } or bool(DAY_FOLDER_PATTERN.fullmatch(name))


def build_settings(root_path: str | Path) -> AppSettings:
    """Create settings for a given trip root."""

    return AppSettings(root_path=Path(root_path).expanduser().resolve())
