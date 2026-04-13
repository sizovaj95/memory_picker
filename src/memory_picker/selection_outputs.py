"""Epic 3 manifest writing and output materialization."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from memory_picker.config import AppSettings
from memory_picker.models import (
    DayCandidatePhoto,
    DaySelectionManifest,
    DaySelectionResult,
    TripSelectedPhoto,
    TripSelectionManifest,
)
from memory_picker.selection import good_enough_prefix, load_cluster_manifest


def write_day_selection_manifest(
    result: DaySelectionResult,
    curation_prompt_name: str | None = None,
    curation_model_name: str | None = None,
    curation_response_id: str | None = None,
) -> DaySelectionManifest:
    """Persist one day's full ranking output for local reuse."""

    candidates_by_id = {candidate.photo_id: candidate for candidate in result.candidates}
    decisions_by_id = {decision.photo_id: decision for decision in result.selection_decisions}
    strong_prefix = good_enough_prefix(result.rankings)
    final_selected_count = sum(
        1
        for decision in result.selection_decisions
        if decision.final_curation_status == "selected"
    )

    payload = {
        "day_name": result.day_name,
        "manifest_version": 2,
        "summary": {
            "candidate_count": len(result.candidates),
            "ranked_count": len(result.rankings),
            "good_enough_count": len(strong_prefix),
            "provisional_selected_count": len(result.provisional_photo_ids),
            "finalist_shortlist_count": len(result.finalist_photo_ids),
            "final_selected_count": final_selected_count,
            "duplicate_rejections": sum(
                1
                for decision in result.selection_decisions
                if decision.final_curation_status == "duplicate_rejected"
            ),
            "cluster_exceptions_used": sum(
                1 for decision in result.selection_decisions if decision.used_cluster_exception
            ),
        },
        "prompt": {
            "prompt_name": result.prompt_name,
            "model_name": result.model_name,
            "curation_prompt_name": curation_prompt_name,
            "curation_model_name": curation_model_name,
        },
        "response_metadata": {
            "response_id": result.response_id,
            "curation_response_id": curation_response_id,
        },
        "candidates": [
            {
                "photo_id": candidate.photo_id,
                "relative_path": str(candidate.relative_path),
                "cluster_id": candidate.cluster_id,
                "burst_group_id": candidate.burst_group_id,
                "captured_at": candidate.captured_at.isoformat(),
                "blur_score": candidate.blur_score,
                "brightness_mean": candidate.brightness_mean,
                "overexposed_ratio": candidate.overexposed_ratio,
            }
            for candidate in result.candidates
        ],
        "rankings": [
            {
                "photo_id": ranking.photo_id,
                "relative_path": str(candidates_by_id[ranking.photo_id].relative_path),
                "cluster_id": candidates_by_id[ranking.photo_id].cluster_id,
                "burst_group_id": candidates_by_id[ranking.photo_id].burst_group_id,
                "rank": ranking.rank,
                "overall_score": ranking.overall_score,
                "technical_quality_score": ranking.technical_quality_score,
                "storytelling_score": ranking.storytelling_score,
                "distinctiveness_score": ranking.distinctiveness_score,
                "theme_tags": list(ranking.theme_tags),
                "rationale": ranking.rationale,
                "is_good_enough": ranking.is_good_enough,
                "normalized_score": ranking.normalized_score,
                "provisional_selected": decisions_by_id.get(ranking.photo_id).provisional_selected
                if decisions_by_id.get(ranking.photo_id)
                else False,
                "finalist_shortlisted": decisions_by_id.get(ranking.photo_id).finalist_shortlisted
                if decisions_by_id.get(ranking.photo_id)
                else False,
                "shortlist_origin": decisions_by_id.get(ranking.photo_id).shortlist_origin
                if decisions_by_id.get(ranking.photo_id)
                else None,
                "final_curation_status": decisions_by_id.get(ranking.photo_id).final_curation_status
                if decisions_by_id.get(ranking.photo_id)
                else "not_shortlisted",
                "duplicate_of_photo_id": decisions_by_id.get(ranking.photo_id).duplicate_of_photo_id
                if decisions_by_id.get(ranking.photo_id)
                else None,
                "used_cluster_exception": decisions_by_id.get(ranking.photo_id).used_cluster_exception
                if decisions_by_id.get(ranking.photo_id)
                else False,
                "final_curation_rank": decisions_by_id.get(ranking.photo_id).final_curation_rank
                if decisions_by_id.get(ranking.photo_id)
                else None,
            }
            for ranking in result.rankings
        ],
    }
    result.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return DaySelectionManifest(
        day_name=result.day_name,
        manifest_path=result.manifest_path,
        candidate_count=len(result.candidates),
        ranked_count=len(result.rankings),
        good_enough_count=len(strong_prefix),
        provisional_selected_count=len(result.provisional_photo_ids),
        finalist_shortlist_count=len(result.finalist_photo_ids),
        final_selected_count=final_selected_count,
    )


def refresh_intermediate_cluster_outputs(
    settings: AppSettings,
    day_paths: list[Path],
) -> None:
    """Copy cluster members into intermediate_clusters/day/cluster folders."""

    intermediate_root = settings.root_path / settings.managed_folders.intermediate_clusters
    if intermediate_root.exists():
        shutil.rmtree(intermediate_root)
    intermediate_root.mkdir(parents=True, exist_ok=True)

    for day_path in sorted(day_paths, key=lambda path: path.name):
        payload = load_cluster_manifest(day_path)
        day_output_dir = intermediate_root / day_path.name
        singleton_members_payload = []
        for cluster in sorted(payload["clusters"], key=lambda item: item["cluster_id"]):
            if len(cluster["members"]) == 1:
                member = cluster["members"][0]
                cluster_output_dir = day_output_dir / "cluster_other"
                cluster_output_dir.mkdir(parents=True, exist_ok=True)
                source_path = settings.root_path / member["relative_path"]
                destination_path = cluster_output_dir / source_path.name
                shutil.copy2(source_path, destination_path)
                singleton_members_payload.append(
                    {
                        "filename": member["filename"],
                        "relative_path": member["relative_path"],
                        "original_cluster_id": cluster["cluster_id"],
                        "burst_group_id": member["burst_group_id"],
                        "captured_at": member["captured_at"],
                        "intermediate_cluster_path": str(
                            destination_path.relative_to(settings.root_path)
                        ),
                    }
                )
                continue

            cluster_output_dir = day_output_dir / cluster["cluster_id"]
            cluster_output_dir.mkdir(parents=True, exist_ok=True)

            members_payload = []
            for member in sorted(
                cluster["members"],
                key=lambda item: (item["captured_at"], item["relative_path"]),
            ):
                source_path = settings.root_path / member["relative_path"]
                destination_path = cluster_output_dir / source_path.name
                shutil.copy2(source_path, destination_path)
                members_payload.append(
                    {
                        "filename": member["filename"],
                        "relative_path": member["relative_path"],
                        "burst_group_id": member["burst_group_id"],
                        "captured_at": member["captured_at"],
                        "intermediate_cluster_path": str(
                            destination_path.relative_to(settings.root_path)
                        ),
                    }
                )

            cluster_manifest = {
                "manifest_version": 1,
                "output_type": "pre_burst_dedup_cluster",
                "day_name": day_path.name,
                "cluster_id": cluster["cluster_id"],
                "summary": {
                    "member_count": len(members_payload),
                    "burst_group_count": len(cluster["burst_group_ids"]),
                },
                "representative_filename": cluster["representative_filename"],
                "burst_group_ids": cluster["burst_group_ids"],
                "members": members_payload,
            }
            manifest_path = cluster_output_dir / "selection_manifest.json"
            manifest_path.write_text(json.dumps(cluster_manifest, indent=2), encoding="utf-8")

        if singleton_members_payload:
            cluster_other_dir = day_output_dir / "cluster_other"
            singleton_cluster_ids = [
                member["original_cluster_id"]
                for member in sorted(
                    singleton_members_payload,
                    key=lambda item: (item["captured_at"], item["relative_path"]),
                )
            ]
            cluster_manifest = {
                "manifest_version": 1,
                "output_type": "pre_burst_dedup_singleton_clusters",
                "day_name": day_path.name,
                "cluster_id": "cluster_other",
                "summary": {
                    "member_count": len(singleton_members_payload),
                    "original_cluster_count": len(singleton_cluster_ids),
                },
                "original_cluster_ids": singleton_cluster_ids,
                "members": sorted(
                    singleton_members_payload,
                    key=lambda item: (item["captured_at"], item["relative_path"]),
                ),
            }
            manifest_path = cluster_other_dir / "selection_manifest.json"
            manifest_path.write_text(json.dumps(cluster_manifest, indent=2), encoding="utf-8")


def refresh_intermediate_result_outputs(
    settings: AppSettings,
    day_candidates: dict[str, list[DayCandidatePhoto]],
) -> TripSelectionManifest:
    """Copy burst-deduplicated photos into intermediate_result/day folders."""

    intermediate_root = settings.root_path / settings.managed_folders.intermediate_result
    if intermediate_root.exists():
        shutil.rmtree(intermediate_root)
    intermediate_root.mkdir(parents=True, exist_ok=True)

    all_candidates = [
        candidate
        for candidates in day_candidates.values()
        for candidate in candidates
    ]
    payload = {
        "manifest_version": 1,
        "output_type": "burst_deduplicated_intermediate_result",
        "summary": {
            "selected_count": len(all_candidates),
            "day_count": len(day_candidates),
            "clusters_represented": len(
                {(candidate.day_name, candidate.cluster_id) for candidate in all_candidates}
            ),
            "burst_groups_represented": len(
                {(candidate.day_name, candidate.burst_group_id) for candidate in all_candidates}
            ),
        },
        "selected_photos": [],
    }

    for day_name, candidates in sorted(day_candidates.items()):
        destination_dir = intermediate_root / day_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        for candidate in sorted(
            candidates,
            key=lambda item: (item.captured_at, str(item.relative_path)),
        ):
            destination_path = destination_dir / candidate.source_path.name
            shutil.copy2(candidate.source_path, destination_path)
            payload["selected_photos"].append(
                {
                    "day_name": candidate.day_name,
                    "photo_id": candidate.photo_id,
                    "relative_path": str(candidate.relative_path),
                    "cluster_id": candidate.cluster_id,
                    "burst_group_id": candidate.burst_group_id,
                    "captured_at": candidate.captured_at.isoformat(),
                    "intermediate_result_path": str(destination_path.relative_to(settings.root_path)),
                }
            )

    manifest_path = intermediate_root / "selection_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return TripSelectionManifest(
        manifest_path=manifest_path,
        selected_count=len(all_candidates),
        clusters_represented=payload["summary"]["clusters_represented"],
    )


def refresh_to_print_outputs(
    settings: AppSettings,
    selected_photos: list[TripSelectedPhoto],
    day_results: list[DaySelectionResult],
    unfilled_capacity_reason: str | None,
    curation_prompt_name: str | None = None,
    curation_model_name: str | None = None,
    curation_response_id: str | None = None,
) -> TripSelectionManifest:
    """Copy final photos into to_print and write the trip-level selection manifest."""

    to_print_root = settings.root_path / settings.managed_folders.to_print
    if to_print_root.exists():
        shutil.rmtree(to_print_root)
    to_print_root.mkdir(parents=True, exist_ok=True)

    prompt_metadata = {
        result.day_name: {
            "prompt_name": result.prompt_name,
            "model_name": result.model_name,
            "response_id": result.response_id,
        }
        for result in day_results
    }
    duplicate_rejections = sum(
        1
        for result in day_results
        for decision in result.selection_decisions
        if decision.final_curation_status == "duplicate_rejected"
    )
    cluster_exceptions_used = sum(
        1
        for result in day_results
        for decision in result.selection_decisions
        if decision.used_cluster_exception
    )

    payload = {
        "manifest_version": 2,
        "summary": {
            "selected_count": len(selected_photos),
            "clusters_represented": len({(photo.day_name, photo.cluster_id) for photo in selected_photos}),
            "duplicate_rejections": duplicate_rejections,
            "cluster_exceptions_used": cluster_exceptions_used,
            "unfilled_capacity_reason": unfilled_capacity_reason,
        },
        "prompt_metadata": prompt_metadata,
        "final_curation_metadata": {
            "prompt_name": curation_prompt_name,
            "model_name": curation_model_name,
            "response_id": curation_response_id,
        },
        "selected_photos": [],
    }
    for photo in selected_photos:
        destination_dir = to_print_root / photo.day_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / photo.source_path.name
        shutil.copy2(photo.source_path, destination_path)
        payload["selected_photos"].append(
            {
                "day_name": photo.day_name,
                "photo_id": photo.photo_id,
                "relative_path": str(photo.relative_path),
                "cluster_id": photo.cluster_id,
                "burst_group_id": photo.burst_group_id,
                "rank": photo.rank,
                "overall_score": photo.overall_score,
                "normalized_score": photo.normalized_score,
                "theme_tags": list(photo.theme_tags),
                "rationale": photo.rationale,
                "shortlist_origin": photo.shortlist_origin,
                "provisional_selected": photo.provisional_selected,
                "used_cluster_exception": photo.used_cluster_exception,
                "final_curation_rank": photo.final_curation_rank,
                "to_print_path": str(destination_path.relative_to(settings.root_path)),
            }
        )

    manifest_path = to_print_root / "selection_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return TripSelectionManifest(
        manifest_path=manifest_path,
        selected_count=len(selected_photos),
        clusters_represented=len({(photo.day_name, photo.cluster_id) for photo in selected_photos}),
        duplicate_rejections=duplicate_rejections,
        cluster_exceptions_used=cluster_exceptions_used,
        unfilled_capacity_reason=unfilled_capacity_reason,
    )
