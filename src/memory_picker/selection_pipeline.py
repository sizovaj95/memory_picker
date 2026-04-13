"""Epic 3 orchestration for burst-deduplicated intermediate materialization."""

from __future__ import annotations

import logging

from memory_picker.config import AppSettings
from memory_picker.models import DayCandidatePhoto, SelectionRunSummary
from memory_picker.selection import (
    build_day_candidates,
    iter_rankable_days,
)
from memory_picker.selection_outputs import (
    refresh_intermediate_cluster_outputs,
    refresh_intermediate_result_outputs,
)

LOGGER = logging.getLogger("memory_picker.selection_pipeline")


def run_selection_pipeline(
    settings: AppSettings,
    ranker: object | None = None,
) -> SelectionRunSummary:
    """Copy all burst-deduplicated cluster survivors into intermediate_result."""

    if not settings.selection_settings.enabled:
        LOGGER.info("Intermediate result materialization is disabled in settings.")
        return SelectionRunSummary()

    day_paths = iter_rankable_days(settings)
    if not day_paths:
        LOGGER.info("No day folders with cluster manifests were found for intermediate results.")
        return SelectionRunSummary()

    if ranker is not None:
        LOGGER.info("Ignoring supplied ranker because intermediate results do not use model ranking.")

    refresh_intermediate_cluster_outputs(settings=settings, day_paths=day_paths)

    day_candidates: dict[str, list[DayCandidatePhoto]] = {}
    candidate_count = 0

    for day_path in day_paths:
        candidates = build_day_candidates(day_path, settings)
        if not candidates:
            continue
        day_candidates[day_path.name] = candidates
        candidate_count += len(candidates)
        LOGGER.info(
            "Prepared %s: burst_deduplicated_candidates=%s",
            day_path.name,
            len(candidates),
        )

    if not day_candidates:
        return SelectionRunSummary()

    trip_manifest = refresh_intermediate_result_outputs(
        settings=settings,
        day_candidates=day_candidates,
    )

    return SelectionRunSummary(
        ranked_days=len(day_candidates),
        ranked_candidates=candidate_count,
        selected_photos=trip_manifest.selected_count,
        day_manifests_written=0,
        trip_manifest_written=trip_manifest.manifest_path.exists(),
    )
