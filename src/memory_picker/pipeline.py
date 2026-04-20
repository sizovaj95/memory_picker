"""End-to-end pipeline orchestration through deterministic post-cluster cleanup."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
from memory_picker.heif_conversion import convert_trip_root_heif_files
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


def _run_quality_assessments(
    photo_records: list[PhotoRecord],
    settings: AppSettings,
) -> list[QualityAssessment]:
    """Run local quality checks, optionally using a bounded thread pool."""

    if not photo_records:
        return []

    total_photos = len(photo_records)
    concurrency_settings = settings.quality_concurrency_settings
    if not concurrency_settings.enabled or total_photos == 1:
        LOGGER.info("Running serial quality checks for %s photos", total_photos)
        assessments: list[QualityAssessment] = []
        for index, record in enumerate(photo_records, start=1):
            assessments.append(assess_photo(record.source_path, settings.quality_thresholds))
            log_progress(
                LOGGER,
                "Processing",
                index,
                total_photos,
                noun="photo",
                interval=concurrency_settings.progress_log_interval,
            )
        LOGGER.info("Completed quality checks: photos=%s workers=%s", total_photos, 1)
        return assessments

    max_workers = max(1, min(concurrency_settings.max_workers, total_photos))
    LOGGER.info(
        "Running concurrent quality checks for %s photos with %s workers",
        total_photos,
        max_workers,
    )
    assessments_by_index: dict[int, QualityAssessment] = {}
    completed_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(assess_photo, record.source_path, settings.quality_thresholds): index
            for index, record in enumerate(photo_records)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            assessments_by_index[index] = future.result()
            completed_count += 1
            log_progress(
                LOGGER,
                "Processing",
                completed_count,
                total_photos,
                noun="photo",
                interval=concurrency_settings.progress_log_interval,
            )

    LOGGER.info("Completed quality checks: photos=%s workers=%s", total_photos, max_workers)
    return [assessments_by_index[index] for index in range(total_photos)]


def run_pipeline(settings: AppSettings, embedder=None, categorizer=None) -> RunSummary:
    """Run intake, clustering, deterministic cleanup, and optional categorization."""

    conversion_summary = convert_trip_root_heif_files(settings)

    LOGGER.info("Stage 1/7: scanning trip root inventory")
    inventory = scan_trip_root(settings)
    photo_items = [item for item in inventory if item.classification == MediaClassification.PHOTO]
    artifact_items = [item for item in inventory if item.classification != MediaClassification.PHOTO]
    LOGGER.info(
        "Completed stage 1/7: total_items=%s photo_items=%s artifact_items=%s",
        len(inventory),
        len(photo_items),
        len(artifact_items),
    )

    LOGGER.info("Stage 2/7: resolving timestamps and day assignments")
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
    LOGGER.info(
        "Completed stage 2/7: photo_records=%s artifacts=%s day_count=%s",
        len(photo_records),
        len(artifact_items),
        len(day_map),
    )

    LOGGER.info("Stage 3/7: running quality checks for %s photos", len(photo_records))
    assessments = _run_quality_assessments(photo_records, settings)
    assessments_by_path = {assessment.source_path: assessment for assessment in assessments}

    LOGGER.info("Stage 4/7: moving files into day folders")
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
    LOGGER.info(
        "Completed stage 4/7: moved_files=%s created_directories=%s",
        file_summary.total_moved,
        file_summary.created_directories,
    )
    LOGGER.info("Stage 5/7: clustering accepted photos")
    clustering_summary = run_clustering_pipeline(settings, embedder=embedder)
    LOGGER.info(
        "Completed stage 5/7: clustered_days=%s final_clusters=%s",
        clustering_summary.clustered_days,
        clustering_summary.cluster_count,
    )
    LOGGER.info("Stage 6/7: post-cluster cleanup")
    cleanup_summary = run_post_cluster_cleanup(settings)
    LOGGER.info(
        "Completed stage 6/7: duplicate_rejections=%s renamed=%s",
        cleanup_summary.duplicate_photos_rejected,
        cleanup_summary.renamed_photos,
    )
    LOGGER.info("Stage 7/7: optional cluster categorization")
    categorization_summary = run_cluster_categorization(settings, categorizer=categorizer)
    LOGGER.info(
        "Completed stage 7/7: categorized_days=%s classified_clusters=%s",
        categorization_summary.categorized_days,
        categorization_summary.classified_clusters,
    )

    summary = RunSummary(
        total_items=len(inventory),
        photo_items=len(photo_items),
        non_photo_items=sum(
            1 for item in inventory if item.classification == MediaClassification.NON_PHOTO
        ),
        unsupported_items=sum(
            1 for item in inventory if item.classification == MediaClassification.UNSUPPORTED
        ),
        converted_heif_files=conversion_summary.converted_files,
        deleted_original_heif_files=conversion_summary.deleted_original_files,
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
        "Run summary: total=%s photos=%s accepted=%s rejected=%s artifacts=%s unsupported=%s converted_heif=%s deleted_heif=%s days=%s moved=%s clustered_days=%s clusters=%s duplicate_rejections=%s renamed=%s classified_clusters=%s categorized_moves=%s",
        summary.total_items,
        summary.photo_items,
        summary.accepted_photos,
        summary.rejected_photos,
        summary.non_photo_items,
        summary.unsupported_items,
        summary.converted_heif_files,
        summary.deleted_original_heif_files,
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
