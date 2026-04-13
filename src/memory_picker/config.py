"""Application configuration and defaults."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from memory_picker import local_settings

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
    intermediate_clusters: str = "intermediate_clusters"
    intermediate_result: str = "intermediate_result"
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
class EmbeddingSettings:
    """Config for the local image embedding backend."""

    backend_name: str = "dinov2"
    model_name: str = "facebook/dinov2-base"
    device: str = "auto"
    batch_size: int = 8


@dataclass(frozen=True)
class ClusteringThresholds:
    """Deterministic and embedding-driven clustering thresholds."""

    burst_time_gap_seconds: int = 60
    perceptual_hash_hamming_threshold: int = 6
    histogram_similarity_threshold: float = 0.92
    semantic_cosine_distance_threshold: float = 0.2


@dataclass(frozen=True)
class SelectionSettings:
    """Config for Epic 3 GPT-backed ranking and final selection."""

    enabled: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    preference_prompt: str | None = None
    max_photos_per_day: int | None = 3
    max_photos_total: int | None = 20
    large_cluster_threshold: int = 5
    allow_spare_capacity_reuse: bool = True
    max_final_photos_per_cluster: int = 1
    max_final_photos_per_cluster_with_exception: int = 2
    second_pass_enabled: bool = True
    second_pass_extra_candidates_per_day: int = 2
    max_ranking_candidates_per_day: int | None = None
    ranking_candidate_sample_seed: int = 17
    openai_upload_max_dimension: int = 1280
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
    selection_settings: SelectionSettings = field(default_factory=SelectionSettings)
    day_prefix: str = "day"
    collision_suffix_separator: str = "__dup"

    def is_managed_directory(self, name: str) -> bool:
        """Return True when the directory is owned by the tool."""

        return name in {
            self.managed_folders.to_print,
            self.managed_folders.intermediate_clusters,
            self.managed_folders.intermediate_result,
            self.managed_folders.rejected,
            self.managed_folders.not_photo,
        } or bool(DAY_FOLDER_PATTERN.fullmatch(name))

def _load_dotenv_files() -> None:
    """Load local .env files without overriding already-set environment variables."""

    repo_root = Path(__file__).resolve().parents[2]
    candidate_paths = [repo_root / ".env"]
    cwd_env = Path.cwd() / ".env"
    if cwd_env not in candidate_paths:
        candidate_paths.append(cwd_env)

    for path in candidate_paths:
        load_dotenv(dotenv_path=path, override=False)


def build_settings(root_path: str | Path) -> AppSettings:
    """Create settings for a given trip root."""

    _load_dotenv_files()
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    selection_settings = SelectionSettings(
        enabled=local_settings.SELECTION_ENABLED,
        openai_api_key=openai_api_key,
        openai_model=local_settings.OPENAI_MODEL,
        preference_prompt=local_settings.SELECTION_PREFERENCE_PROMPT,
        max_photos_per_day=local_settings.MAX_PHOTOS_PER_DAY,
        max_photos_total=local_settings.MAX_PHOTOS_TOTAL,
        large_cluster_threshold=local_settings.LARGE_CLUSTER_THRESHOLD,
        allow_spare_capacity_reuse=local_settings.ALLOW_SPARE_CAPACITY_REUSE,
        max_final_photos_per_cluster=local_settings.MAX_FINAL_PHOTOS_PER_CLUSTER,
        max_final_photos_per_cluster_with_exception=local_settings.MAX_FINAL_PHOTOS_PER_CLUSTER_WITH_EXCEPTION,
        second_pass_enabled=local_settings.SECOND_PASS_ENABLED,
        second_pass_extra_candidates_per_day=local_settings.SECOND_PASS_EXTRA_CANDIDATES_PER_DAY,
        max_ranking_candidates_per_day=local_settings.MAX_RANKING_CANDIDATES_PER_DAY,
        ranking_candidate_sample_seed=local_settings.RANKING_CANDIDATE_SAMPLE_SEED,
        openai_upload_max_dimension=local_settings.OPENAI_UPLOAD_MAX_DIMENSION,
        openai_upload_jpeg_quality=local_settings.OPENAI_UPLOAD_JPEG_QUALITY,
    )

    return AppSettings(
        root_path=Path(root_path).expanduser().resolve(),
        selection_settings=selection_settings,
    )
