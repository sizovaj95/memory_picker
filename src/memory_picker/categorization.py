"""Epic 4 optional OpenAI-backed cluster categorization."""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps

from memory_picker.config import AppSettings, CategoryDefinition, CategorizationSettings
from memory_picker.image_support import register_heif_support
from memory_picker.logging_utils import log_progress
from memory_picker.models import (
    CategorizationRunSummary,
    ClusterCategorizationResult,
)
from memory_picker.post_cluster_cleanup import load_cluster_manifest
from memory_picker.preprocessing import iter_day_directories

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only when the optional dependency is missing.
    OpenAI = None

LOGGER = logging.getLogger("memory_picker.categorization")


class ClusterCategorizer(Protocol):
    """Interface for classifying one representative image per cluster."""

    def categorize_cluster(
        self,
        day_name: str,
        cluster: dict,
        image_path: Path,
        categorization_settings: CategorizationSettings,
    ) -> ClusterCategorizationResult:
        """Return one category assignment for the provided cluster representative."""


def build_default_categorizer(settings: AppSettings) -> ClusterCategorizer:
    """Build the default OpenAI-backed cluster categorizer."""

    api_key = settings.categorization_settings.openai_api_key
    if not api_key:
        raise RuntimeError(
            "Epic 4 categorization is enabled but no OPENAI_API_KEY was found in the environment."
        )
    return OpenAIClusterCategorizer(
        api_key=api_key,
        model_name=settings.categorization_settings.openai_model,
    )


def build_category_prompt(categories: tuple[CategoryDefinition, ...]) -> str:
    """Build the categorization prompt from the configured taxonomy."""

    lines = [
        "Classify this travel photo into exactly one configured category.",
        "The image may represent an entire cluster of similar photos, so choose the single best category for the cluster.",
        "Use the category rules below exactly as guidance.",
    ]
    for category in categories:
        lines.append(f"- {category.name}: {category.rule}")
    lines.append("Always choose one category from the configured list.")
    lines.append("Use 'other' when none of the configured categories fit clearly.")
    lines.append("Keep the rationale short, one sentence maximum.")
    return "\n".join(lines)


def build_category_schema(categories: tuple[CategoryDefinition, ...]) -> dict:
    """Return the strict schema for one cluster categorization response."""

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category_name": {
                "type": "string",
                "enum": [category.name for category in categories],
            },
            "rationale": {"type": "string"},
        },
        "required": ["category_name", "rationale"],
    }


class OpenAIClusterCategorizer:
    """OpenAI-backed categorizer for one representative image per cluster."""

    def __init__(self, api_key: str, model_name: str) -> None:
        if OpenAI is None:
            raise RuntimeError(
                "The openai package is not installed. Add it to the environment before running Epic 4."
            )
        self._client = OpenAI(api_key=api_key)
        self._model_name = model_name

    def categorize_cluster(
        self,
        day_name: str,
        cluster: dict,
        image_path: Path,
        categorization_settings: CategorizationSettings,
    ) -> ClusterCategorizationResult:
        image_input = _build_openai_image_input(
            image_path=image_path,
            max_dimension=categorization_settings.openai_upload_max_dimension,
            jpeg_quality=categorization_settings.openai_upload_jpeg_quality,
        )
        response = self._client.responses.create(
            model=self._model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_category_prompt(categorization_settings.categories),
                        },
                        {
                            "type": "input_text",
                            "text": f"Day: {day_name}\nCluster: {cluster['cluster_id']}",
                        },
                        image_input,
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "cluster_category",
                    "strict": True,
                    "schema": build_category_schema(categorization_settings.categories),
                }
            },
            max_output_tokens=200,
        )
        payload = json.loads(response.output_text)
        return ClusterCategorizationResult(
            category_name=payload["category_name"],
            rationale=payload["rationale"],
            model_name=self._model_name,
            response_id=response.id,
        )


def run_cluster_categorization(
    settings: AppSettings,
    categorizer: ClusterCategorizer | None = None,
) -> CategorizationRunSummary:
    """Classify cleaned clusters and move accepted photos into per-day category folders."""

    if not settings.categorization_settings.enabled:
        LOGGER.info("Epic 4 categorization is disabled in settings.")
        return CategorizationRunSummary()

    day_paths = [
        day_path
        for day_path in iter_day_directories(settings)
        if (day_path / "cluster_manifest.json").exists()
    ]
    if not day_paths:
        return CategorizationRunSummary()

    active_categorizer = categorizer or build_default_categorizer(settings)
    summary = CategorizationRunSummary()
    for day_path in day_paths:
        day_summary = _categorize_day(day_path, settings, active_categorizer)
        summary = CategorizationRunSummary(
            categorized_days=summary.categorized_days + day_summary.categorized_days,
            classified_clusters=summary.classified_clusters + day_summary.classified_clusters,
            photos_moved=summary.photos_moved + day_summary.photos_moved,
            manifests_rewritten=summary.manifests_rewritten + day_summary.manifests_rewritten,
        )
    return summary


def _categorize_day(
    day_path: Path,
    settings: AppSettings,
    categorizer: ClusterCategorizer,
) -> CategorizationRunSummary:
    payload = load_cluster_manifest(day_path)
    cluster_results: dict[str, tuple[ClusterCategorizationResult, str]] = {}
    cluster_candidates = [
        cluster for cluster in payload["clusters"] if _accepted_cluster_members(cluster, settings)
    ]
    LOGGER.info("Categorizing %s clusters for %s", len(cluster_candidates), day_path.name)

    for index, cluster in enumerate(cluster_candidates, start=1):
        accepted_members = _accepted_cluster_members(cluster, settings)
        source_member = _choose_classification_member(cluster, accepted_members)
        image_path = (settings.root_path / source_member["relative_path"]).resolve()
        result = categorizer.categorize_cluster(
            day_name=day_path.name,
            cluster=cluster,
            image_path=image_path,
            categorization_settings=settings.categorization_settings,
        )
        cluster_results[cluster["cluster_id"]] = (result, source_member["filename"])
        log_progress(LOGGER, "Categorizing", index, len(cluster_candidates), noun="cluster")

    photos_moved = _move_cluster_members_to_category_folders(day_path, payload, cluster_results, settings)
    rewritten_payload = _rewrite_categorized_manifest_payload(
        payload=payload,
        day_name=day_path.name,
        cluster_results=cluster_results,
        settings=settings,
    )
    manifest_path = day_path / "cluster_manifest.json"
    manifest_path.write_text(json.dumps(rewritten_payload, indent=2), encoding="utf-8")

    LOGGER.info(
        "Categorized %s: clusters=%s photos_moved=%s",
        day_path.name,
        len(cluster_results),
        photos_moved,
    )
    return CategorizationRunSummary(
        categorized_days=1,
        classified_clusters=len(cluster_results),
        photos_moved=photos_moved,
        manifests_rewritten=1,
    )


def _accepted_cluster_members(cluster: dict, settings: AppSettings) -> list[dict]:
    excluded_folder_names = {
        settings.managed_folders.rejected,
        settings.managed_folders.not_photo,
    }
    return [
        member
        for member in cluster["members"]
        if not any(part in excluded_folder_names for part in Path(member["relative_path"]).parts[1:-1])
    ]


def _choose_classification_member(cluster: dict, accepted_members: list[dict]) -> dict:
    for member in accepted_members:
        if member["filename"] == cluster["representative_filename"]:
            return member
    return sorted(accepted_members, key=lambda member: member["relative_path"])[0]


def _move_cluster_members_to_category_folders(
    day_path: Path,
    payload: dict,
    cluster_results: dict[str, tuple[ClusterCategorizationResult, str]],
    settings: AppSettings,
) -> int:
    """Move accepted cluster members into their per-day category folders."""

    moved_count = 0
    for cluster in payload["clusters"]:
        categorization = cluster_results.get(cluster["cluster_id"])
        if categorization is None:
            continue
        category_name = categorization[0].category_name
        destination_dir = day_path / category_name
        destination_dir.mkdir(parents=True, exist_ok=True)

        for member in _accepted_cluster_members(cluster, settings):
            source_path = (settings.root_path / member["relative_path"]).resolve()
            destination_path = (destination_dir / member["filename"]).resolve()
            if source_path == destination_path:
                continue
            if destination_path.exists():
                raise RuntimeError(f"Category destination already exists: {destination_path}")
            source_path.rename(destination_path)
            moved_count += 1
    return moved_count


def _rewrite_categorized_manifest_payload(
    payload: dict,
    day_name: str,
    cluster_results: dict[str, tuple[ClusterCategorizationResult, str]],
    settings: AppSettings,
) -> dict:
    """Rewrite a day manifest so accepted members live under category folders."""

    category_counts: dict[str, int] = {}
    rewritten_clusters: list[dict] = []
    for cluster in payload["clusters"]:
        categorization = cluster_results.get(cluster["cluster_id"])
        if categorization is None:
            continue
        result, source_filename = categorization
        rewritten_members = []
        for member in _accepted_cluster_members(cluster, settings):
            rewritten_relative_path = str(Path(day_name) / result.category_name / member["filename"])
            rewritten_members.append(
                {
                    **member,
                    "relative_path": rewritten_relative_path,
                }
            )
        if not rewritten_members:
            continue
        category_counts[result.category_name] = category_counts.get(result.category_name, 0) + len(rewritten_members)
        rewritten_clusters.append(
            {
                **cluster,
                "category_name": result.category_name,
                "classification_rationale": result.rationale,
                "classification_source_filename": source_filename,
                "classification_model_name": result.model_name,
                "classification_response_id": result.response_id,
                "members": rewritten_members,
            }
        )

    return {
        "day_name": day_name,
        "manifest_version": max(int(payload.get("manifest_version", 1)), 2),
        "summary": {
            "accepted_photo_count": sum(cluster["member_count"] for cluster in rewritten_clusters),
            "burst_group_count": len(payload["burst_groups"]),
            "cluster_count": len(rewritten_clusters),
            "singleton_cluster_count": sum(
                1 for cluster in rewritten_clusters if cluster["member_count"] == 1
            ),
            "categorized_cluster_count": len(rewritten_clusters),
            "category_counts": category_counts,
        },
        "burst_groups": payload["burst_groups"],
        "clusters": rewritten_clusters,
        "generated_from": payload["generated_from"],
    }


def _build_openai_image_input(
    image_path: Path,
    max_dimension: int,
    jpeg_quality: int,
) -> dict:
    """Build a resized JPEG data URL payload for one OpenAI vision request."""

    register_heif_support()
    with Image.open(image_path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        normalized.thumbnail((max_dimension, max_dimension))
        buffer = io.BytesIO()
        normalized.save(buffer, format="JPEG", quality=jpeg_quality)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:image/jpeg;base64,{encoded}",
        "detail": "low",
    }
