"""End-to-end pipeline orchestration through deterministic post-cluster cleanup."""

from __future__ import annotations

import logging

from memory_picker.categorization import run_cluster_categorization
from memory_picker.cluster_pipeline import run_clustering_pipeline
from memory_picker.config import AppSettings
from memory_picker.day_assignment import (
    assign_day,
    build_day_assignments,
    build_day_map,
    infer_filesystem_datetime,
    resolve_photo_record,
)
from memory_picker.file_actions import apply_move_plans
from memory_picker.inventory import scan_trip_root
from memory_picker.logging_utils import log_progress
from memory_picker.models import (
    DestinationCategory,
    FileMovePlan,
    MediaClassification,
    PhotoRecord,
    QualityAssessment,
    RejectionReason,
    RunSummary,
    TimestampSource,
)
from memory_picker.post_cluster_cleanup import run_post_cluster_cleanup
from memory_picker.preprocessing import iter_day_directories
from memory_picker.quality import assess_photo

LOGGER = logging.getLogger("memory_picker.pipeline")


def _build_photo_move_plan(
    record: PhotoRecord,
    day_name: str,
    assessment: QualityAssessment,
    settings: AppSettings,
) -> FileMovePlan:
    """Build the day move plan for one photo after quality assessment."""

    if assessment.is_accepted:
        return FileMovePlan(
            source_path=record.source_path,
            day_name=day_name,
            destination_category=DestinationCategory.ACCEPTED,
        )

    destination_subfolder = settings.managed_folders.low_quality
    if RejectionReason.CORRUPT in assessment.rejection_reasons:
        destination_subfolder = settings.managed_folders.not_photo
    return FileMovePlan(
        source_path=record.source_path,
        day_name=day_name,
        destination_category=DestinationCategory.REJECTED,
        destination_subfolder=destination_subfolder,
    )


def run_pipeline(settings: AppSettings, embedder=None, categorizer=None) -> RunSummary:
    """Run intake, clustering, deterministic cleanup, and optional categorization."""

    LOGGER.info("Stage 1/6: scanning trip root inventory")
    inventory = scan_trip_root(settings)
    photo_items = [item for item in inventory if item.classification == MediaClassification.PHOTO]
    artifact_items = [item for item in inventory if item.classification != MediaClassification.PHOTO]

    LOGGER.info("Stage 2/6: resolving timestamps and day assignments")
    photo_records = [resolve_photo_record(item) for item in photo_items]
    artifact_dates = {
        item.source_path: infer_filesystem_datetime(item.source_path).date() for item in artifact_items
    }

    all_dates = [record.captured_on for record in photo_records] + list(artifact_dates.values())
    day_map = build_day_map(all_dates, settings)

    photo_assignments = build_day_assignments(photo_records, day_map)
    photo_assignments_by_path = {
        assignment.source_path: assignment for assignment in photo_assignments
    }

    LOGGER.info("Stage 3/6: running quality checks for %s photos", len(photo_records))
    assessments: list[QualityAssessment] = []
    for index, record in enumerate(photo_records, start=1):
        assessments.append(assess_photo(record.source_path, settings.quality_thresholds))
        log_progress(LOGGER, "Processing", index, len(photo_records), noun="photo")
    assessments_by_path = {assessment.source_path: assessment for assessment in assessments}

    LOGGER.info("Stage 4/6: moving files into day folders")
    move_plans: list[FileMovePlan] = []
    for record in photo_records:
        assignment = photo_assignments_by_path[record.source_path]
        assessment = assessments_by_path[record.source_path]
        move_plans.append(_build_photo_move_plan(record, assignment.day_name, assessment, settings))

    for item in artifact_items:
        captured_on = artifact_dates[item.source_path]
        artifact_assignment = assign_day(
            source_path=item.source_path,
            captured_on=captured_on,
            timestamp_source=TimestampSource.MTIME,
            day_map=day_map,
        )
        move_plans.append(
            FileMovePlan(
                source_path=item.source_path,
                day_name=artifact_assignment.day_name,
                destination_category=DestinationCategory.NOT_PHOTO,
            )
        )

    file_summary = apply_move_plans(settings, move_plans)
    LOGGER.info("Stage 5/6: clustering accepted photos")
    clustering_summary = run_clustering_pipeline(settings, embedder=embedder)
    LOGGER.info("Stage 6/6: post-cluster cleanup")
    cleanup_summary = run_post_cluster_cleanup(settings)
    LOGGER.info("Optional stage: cluster categorization")
    categorization_summary = run_cluster_categorization(settings, categorizer=categorizer)

    summary = RunSummary(
        total_items=len(inventory),
        photo_items=len(photo_items),
        non_photo_items=sum(
            1 for item in inventory if item.classification == MediaClassification.NON_PHOTO
        ),
        unsupported_items=sum(
            1 for item in inventory if item.classification == MediaClassification.UNSUPPORTED
        ),
        accepted_photos=sum(1 for assessment in assessments if assessment.is_accepted),
        rejected_photos=sum(1 for assessment in assessments if not assessment.is_accepted),
        day_count=len(iter_day_directories(settings)),
        moved_files=file_summary.total_moved,
        created_directories=file_summary.created_directories,
        clustered_days=clustering_summary.clustered_days,
        burst_group_count=clustering_summary.burst_group_count,
        final_cluster_count=clustering_summary.cluster_count,
        manifests_written=clustering_summary.manifests_written,
        duplicate_photos_rejected=cleanup_summary.duplicate_photos_rejected,
        renamed_photos=cleanup_summary.renamed_photos,
        cleanup_manifests_rewritten=cleanup_summary.manifests_rewritten,
        categorized_days=categorization_summary.categorized_days,
        classified_clusters=categorization_summary.classified_clusters,
        categorized_photos_moved=categorization_summary.photos_moved,
        categorization_manifests_rewritten=categorization_summary.manifests_rewritten,
    )

    LOGGER.info(
        "Run summary: total=%s photos=%s accepted=%s rejected=%s artifacts=%s unsupported=%s days=%s moved=%s clustered_days=%s clusters=%s duplicate_rejections=%s renamed=%s classified_clusters=%s categorized_moves=%s",
        summary.total_items,
        summary.photo_items,
        summary.accepted_photos,
        summary.rejected_photos,
        summary.non_photo_items,
        summary.unsupported_items,
        summary.day_count,
        summary.moved_files,
        summary.clustered_days,
        summary.final_cluster_count,
        summary.duplicate_photos_rejected,
        summary.renamed_photos,
        summary.classified_clusters,
        summary.categorized_photos_moved,
    )
    return summary
