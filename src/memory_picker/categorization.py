"""Epic 4 optional OpenAI-backed cluster categorization."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from pathlib import Path
from time import perf_counter
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
    from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError, RateLimitError
except ImportError:  # pragma: no cover - exercised only when the optional dependency is missing.
    APIConnectionError = None
    APITimeoutError = None
    AsyncOpenAI = None
    InternalServerError = None
    RateLimitError = None

LOGGER = logging.getLogger("memory_picker.categorization")


class ClusterCategorizer(Protocol):
    """Interface for classifying one representative image per cluster."""

    async def acategorize_cluster(
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
        if AsyncOpenAI is None:
            raise RuntimeError(
                "The openai package is not installed. Add it to the environment before running Epic 4."
            )
        self._client = AsyncOpenAI(api_key=api_key)
        self._model_name = model_name

    async def acategorize_cluster(
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
        response = await self._client.responses.create(
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

    stage_started_at = perf_counter()
    if not settings.categorization_settings.enabled:
        LOGGER.info("Epic 4 categorization is disabled in settings. elapsed_seconds=%.2f", 0.0)
        return CategorizationRunSummary()

    day_paths = [
        day_path
        for day_path in iter_day_directories(settings)
        if (day_path / "cluster_manifest.json").exists()
    ]
    if not day_paths:
        LOGGER.info("Epic 4 categorization found no day manifests to process. elapsed_seconds=%.2f", 0.0)
        return CategorizationRunSummary()

    active_categorizer = categorizer or build_default_categorizer(settings)
    LOGGER.info(
        "Epic 4 categorization is enabled: concurrency_limit=%s max_retries=%s",
        settings.categorization_concurrency_settings.max_concurrent_requests,
        settings.categorization_concurrency_settings.max_retries,
    )
    summary = CategorizationRunSummary()
    for day_path in day_paths:
        day_summary = _categorize_day(day_path, settings, active_categorizer)
        summary = CategorizationRunSummary(
            categorized_days=summary.categorized_days + day_summary.categorized_days,
            classified_clusters=summary.classified_clusters + day_summary.classified_clusters,
            photos_moved=summary.photos_moved + day_summary.photos_moved,
            manifests_rewritten=summary.manifests_rewritten + day_summary.manifests_rewritten,
        )
    LOGGER.info(
        "Completed Epic 4 categorization: categorized_days=%s classified_clusters=%s photos_moved=%s manifests_rewritten=%s elapsed_seconds=%.2f",
        summary.categorized_days,
        summary.classified_clusters,
        summary.photos_moved,
        summary.manifests_rewritten,
        perf_counter() - stage_started_at,
    )
    return summary


def _categorize_day(
    day_path: Path,
    settings: AppSettings,
    categorizer: ClusterCategorizer,
) -> CategorizationRunSummary:
    payload = load_cluster_manifest(day_path)
    cluster_candidates = [
        (cluster, _choose_classification_member(cluster, accepted_members))
        for cluster in payload["clusters"]
        if (accepted_members := _accepted_cluster_members(cluster, settings))
    ]
    LOGGER.info("Categorizing %s clusters for %s", len(cluster_candidates), day_path.name)
    try:
        cluster_results, retry_count = asyncio.run(
            _collect_cluster_results_async(
                day_path=day_path,
                cluster_candidates=cluster_candidates,
                settings=settings,
                categorizer=categorizer,
            )
        )
    except Exception as exc:
        LOGGER.error("Categorization failed for %s: %s", day_path.name, exc)
        raise

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
        "Categorized %s: clusters=%s photos_moved=%s retries=%s concurrency_limit=%s",
        day_path.name,
        len(cluster_results),
        photos_moved,
        retry_count,
        _categorization_request_limit(settings),
    )
    return CategorizationRunSummary(
        categorized_days=1,
        classified_clusters=len(cluster_results),
        photos_moved=photos_moved,
        manifests_rewritten=1,
    )


async def _collect_cluster_results_async(
    day_path: Path,
    cluster_candidates: list[tuple[dict, dict]],
    settings: AppSettings,
    categorizer: ClusterCategorizer,
) -> tuple[dict[str, tuple[ClusterCategorizationResult, str]], int]:
    """Collect cluster categorization results concurrently before mutating the filesystem."""

    concurrency_limit = _categorization_request_limit(settings)
    semaphore = asyncio.Semaphore(concurrency_limit)
    tasks = [
        asyncio.create_task(
            _categorize_cluster_candidate_async(
                day_name=day_path.name,
                cluster=cluster,
                source_member=source_member,
                settings=settings,
                categorizer=categorizer,
                semaphore=semaphore,
            )
        )
        for cluster, source_member in cluster_candidates
    ]
    cluster_results: dict[str, tuple[ClusterCategorizationResult, str]] = {}
    retry_count = 0
    completed_count = 0
    try:
        for task in asyncio.as_completed(tasks):
            cluster_id, result, source_filename, retries_used = await task
            cluster_results[cluster_id] = (result, source_filename)
            retry_count += retries_used
            completed_count += 1
            log_progress(
                LOGGER,
                "Categorizing",
                completed_count,
                len(cluster_candidates),
                noun="cluster",
                interval=settings.categorization_concurrency_settings.progress_log_interval,
            )
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return cluster_results, retry_count


async def _categorize_cluster_candidate_async(
    day_name: str,
    cluster: dict,
    source_member: dict,
    settings: AppSettings,
    categorizer: ClusterCategorizer,
    semaphore: asyncio.Semaphore,
) -> tuple[str, ClusterCategorizationResult, str, int]:
    """Categorize one cluster representative with retry and bounded concurrency."""

    async with semaphore:
        image_path = (settings.root_path / source_member["relative_path"]).resolve()
        result, retries_used = await _categorize_cluster_with_retries(
            categorizer=categorizer,
            day_name=day_name,
            cluster=cluster,
            image_path=image_path,
            settings=settings,
        )
    return cluster["cluster_id"], result, source_member["filename"], retries_used


async def _categorize_cluster_with_retries(
    categorizer: ClusterCategorizer,
    day_name: str,
    cluster: dict,
    image_path: Path,
    settings: AppSettings,
) -> tuple[ClusterCategorizationResult, int]:
    """Categorize one cluster representative, retrying only transient OpenAI failures."""

    retries_used = 0
    concurrency_settings = settings.categorization_concurrency_settings
    for attempt in range(concurrency_settings.max_retries + 1):
        try:
            result = await categorizer.acategorize_cluster(
                day_name=day_name,
                cluster=cluster,
                image_path=image_path,
                categorization_settings=settings.categorization_settings,
            )
            return result, retries_used
        except Exception as exc:
            if attempt >= concurrency_settings.max_retries or not _is_retryable_categorization_error(exc):
                raise
            retries_used += 1
            delay_seconds = concurrency_settings.initial_retry_delay_seconds * (2**attempt)
            LOGGER.warning(
                "Retrying cluster categorization for %s in %s after %s: %s",
                cluster["cluster_id"],
                day_name,
                f"{delay_seconds:.2f}s",
                exc,
            )
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"Unreachable categorization retry state for {cluster['cluster_id']}")


def _categorization_request_limit(settings: AppSettings) -> int:
    """Return the effective concurrent request limit for OpenAI categorization."""

    concurrency_settings = settings.categorization_concurrency_settings
    if not concurrency_settings.enabled:
        return 1
    return max(1, concurrency_settings.max_concurrent_requests)


def _is_retryable_categorization_error(exc: Exception) -> bool:
    """Return True for transient OpenAI request failures that are safe to retry."""

    retryable_types = tuple(
        exception_type
        for exception_type in (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )
        if exception_type is not None
    )
    return isinstance(exc, retryable_types)


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
