"""Application configuration and defaults."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

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
    rejected: str = "_rejected"
    low_quality: str = "low_quality"
    not_photo: str = "not_photo"
    duplicates: str = "duplicates"


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
class EmbeddingSettings:
    """Config for the local image embedding backend."""

    backend_name: str = "dinov2"
    model_name: str = "facebook/dinov2-base"
    device: str = "auto"
    batch_size: int = 8


@dataclass(frozen=True)
class ClusteringThresholds:
    """Deterministic and embedding-driven clustering thresholds."""

    burst_time_gap_seconds: int = 120
    perceptual_hash_hamming_threshold: int = 6
    histogram_similarity_threshold: float = 0.92
    semantic_cosine_distance_threshold: float = 0.18


@dataclass(frozen=True)
class CleanupSettings:
    """Config for deterministic post-cluster duplicate cleanup."""

    enabled: bool = True
    duplicate_similarity_threshold: float = 0.99
    duplicate_compare_size: int = 256


@dataclass(frozen=True)
class CategoryDefinition:
    """One configurable AI categorization label plus its guidance."""

    name: str
    rule: str


DEFAULT_CATEGORY_DEFINITIONS = (
    CategoryDefinition(
        name="people",
        rule=(
            "Only use when person or people are clearly meant to be in the photo, occupy a sizable "
            "part of it, or are obviously posed subjects, like portraits or selfies. Prefer people over other classes unless "
            "another subject clearly dominates."
        ),
    ),
    CategoryDefinition(name="animals", rule="Use when an animal is the intended subject."),
    CategoryDefinition(name="food", rule="Use when food is the intended subject."),
    CategoryDefinition(
        name="nature",
        rule="Use for nature alone such as forests, mountains, and rivers, without meaningful buildings.",
    ),
    CategoryDefinition(
        name="city",
        rule="Use for city landscapes, streets, and urban scenes that may include many people or greenery.",
    ),
    CategoryDefinition(
        name="architecture",
        rule=(
            "Use when the photo is clearly meant to capture a building, architectural structure, "
            "or monument, such as torii gates."
        ),
    ),
    CategoryDefinition(
        name="other",
        rule="Use for anything that does not fit the configured categories clearly.",
    ),
)


@dataclass(frozen=True)
class CategorizationSettings:
    """Config for optional OpenAI-backed post-cleanup categorization."""

    enabled: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    categories: tuple[CategoryDefinition, ...] = field(default_factory=lambda: DEFAULT_CATEGORY_DEFINITIONS)
    openai_upload_max_dimension: int = 1024
    openai_upload_jpeg_quality: int = 82


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
    embedding_settings: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    clustering_thresholds: ClusteringThresholds = field(default_factory=ClusteringThresholds)
    cleanup_settings: CleanupSettings = field(default_factory=CleanupSettings)
    categorization_settings: CategorizationSettings = field(default_factory=CategorizationSettings)
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

    resolved_root_path = Path(root_path).expanduser().resolve()
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    else:
        fallback_dotenv_path = resolved_root_path / ".env"
        if fallback_dotenv_path.exists():
            load_dotenv(dotenv_path=fallback_dotenv_path, override=False)

    return AppSettings(
        root_path=resolved_root_path,
        categorization_settings=CategorizationSettings(
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        ),
    )
