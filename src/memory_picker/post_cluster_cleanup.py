"""Epic 3 deterministic cleanup for duplicate rejection and survivor renaming."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from memory_picker.config import AppSettings, CleanupSettings
from memory_picker.file_actions import apply_move_plans
from memory_picker.image_support import register_heif_support
from memory_picker.models import CleanupRunSummary, DestinationCategory, FileMovePlan
from memory_picker.preprocessing import iter_day_directories

LOGGER = logging.getLogger("memory_picker.post_cluster_cleanup")

CLUSTER_ID_PATTERN = re.compile(r"^cluster(\d+)$")
BURST_GROUP_ID_PATTERN = re.compile(r"^burst(\d+)$")


@dataclass
class _DisjointSet:
    parent: dict[int, int]

    @classmethod
    def create(cls, size: int) -> "_DisjointSet":
        return cls(parent={index: index for index in range(size)})

    def find(self, index: int) -> int:
        root = self.parent[index]
        if root != index:
            self.parent[index] = self.find(root)
        return self.parent[index]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def load_cluster_manifest(day_path: Path) -> dict:
    """Load the current cluster manifest for a day folder."""

    manifest_path = day_path / "cluster_manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def run_post_cluster_cleanup(settings: AppSettings) -> CleanupRunSummary:
    """Apply deterministic duplicate rejection and survivor renaming after clustering."""

    if not settings.cleanup_settings.enabled:
        LOGGER.info("Epic 3 deterministic cleanup is disabled in settings.")
        return CleanupRunSummary()

    summary = CleanupRunSummary()
    day_paths = [
        day_path
        for day_path in iter_day_directories(settings)
        if (day_path / "cluster_manifest.json").exists()
    ]
    for day_path in day_paths:
        day_summary = _cleanup_day(day_path, settings)
        summary = CleanupRunSummary(
            processed_days=summary.processed_days + day_summary.processed_days,
            duplicate_photos_rejected=(
                summary.duplicate_photos_rejected + day_summary.duplicate_photos_rejected
            ),
            renamed_photos=summary.renamed_photos + day_summary.renamed_photos,
            manifests_rewritten=summary.manifests_rewritten + day_summary.manifests_rewritten,
        )
    return summary


def _cleanup_day(day_path: Path, settings: AppSettings) -> CleanupRunSummary:
    """Clean one day folder by rejecting duplicates, renaming survivors, and rewriting its manifest."""

    payload = load_cluster_manifest(day_path)
    image_cache: dict[Path, np.ndarray] = {}
    loser_relative_paths = _collect_duplicate_losers(day_path, payload, settings, image_cache)

    loser_move_plans = [
        FileMovePlan(
            source_path=(settings.root_path / relative_path).resolve(),
            day_name=day_path.name,
            destination_category=DestinationCategory.REJECTED,
        )
        for relative_path in sorted(loser_relative_paths)
    ]
    apply_move_plans(settings, loser_move_plans)

    rename_lookup = _rename_surviving_members(day_path, payload, loser_relative_paths, settings)
    rewritten_payload = _rewrite_cluster_manifest_payload(
        payload=payload,
        day_name=day_path.name,
        rename_lookup=rename_lookup,
        loser_relative_paths=loser_relative_paths,
    )
    manifest_path = day_path / "cluster_manifest.json"
    manifest_path.write_text(json.dumps(rewritten_payload, indent=2), encoding="utf-8")

    renamed_photos = sum(
        1 for old_relative_path, new_relative_path in rename_lookup.items() if old_relative_path != new_relative_path
    )
    LOGGER.info(
        "Cleaned %s: duplicate_rejections=%s renamed=%s survivors=%s",
        day_path.name,
        len(loser_relative_paths),
        renamed_photos,
        rewritten_payload["summary"]["accepted_photo_count"],
    )
    return CleanupRunSummary(
        processed_days=1,
        duplicate_photos_rejected=len(loser_relative_paths),
        renamed_photos=renamed_photos,
        manifests_rewritten=1,
    )


def _collect_duplicate_losers(
    day_path: Path,
    payload: dict,
    settings: AppSettings,
    image_cache: dict[Path, np.ndarray],
) -> set[str]:
    """Return relative paths for duplicate photos that lose their within-burst comparison."""

    loser_relative_paths: set[str] = set()

    for cluster in payload["clusters"]:
        members_by_burst_group: dict[str, list[dict]] = defaultdict(list)
        for member in cluster["members"]:
            members_by_burst_group[member["burst_group_id"]].append(member)

        for burst_group_id in cluster["burst_group_ids"]:
            burst_members = sorted(
                members_by_burst_group.get(burst_group_id, ()),
                key=lambda member: (member["captured_at"], member["relative_path"]),
            )
            if len(burst_members) <= 1:
                continue

            duplicate_sets = _find_duplicate_sets(day_path, burst_members, settings.cleanup_settings, image_cache)
            for duplicate_set in duplicate_sets:
                winner = _choose_duplicate_winner(duplicate_set)
                for member in duplicate_set:
                    if member["relative_path"] != winner["relative_path"]:
                        loser_relative_paths.add(member["relative_path"])

    return loser_relative_paths


def _find_duplicate_sets(
    day_path: Path,
    members: list[dict],
    settings: CleanupSettings,
    image_cache: dict[Path, np.ndarray],
) -> list[list[dict]]:
    """Group connected duplicate members using the configured pixel-similarity threshold."""

    disjoint_set = _DisjointSet.create(len(members))

    for left_index, left_member in enumerate(members):
        left_path = (day_path.parent / left_member["relative_path"]).resolve()
        for right_index in range(left_index + 1, len(members)):
            right_member = members[right_index]
            right_path = (day_path.parent / right_member["relative_path"]).resolve()
            similarity = compute_visual_similarity(
                left_path=left_path,
                right_path=right_path,
                compare_size=settings.duplicate_compare_size,
                image_cache=image_cache,
            )
            if similarity >= settings.duplicate_similarity_threshold:
                disjoint_set.union(left_index, right_index)

    grouped_members: dict[int, list[dict]] = defaultdict(list)
    for index, member in enumerate(members):
        grouped_members[disjoint_set.find(index)].append(member)

    return [
        sorted(group, key=_duplicate_winner_sort_key)
        for group in grouped_members.values()
        if len(group) > 1
    ]


def _choose_duplicate_winner(duplicate_set: list[dict]) -> dict:
    """Return the deterministic winner from one connected duplicate set."""

    return sorted(duplicate_set, key=_duplicate_winner_sort_key)[0]


def _duplicate_winner_sort_key(member: dict) -> tuple[float, str, str]:
    """Sort duplicate candidates by blur, then capture time, then stable path order."""

    return (
        -(member.get("blur_score") or 0.0),
        member["captured_at"],
        member["relative_path"],
    )


def compute_visual_similarity(
    left_path: Path,
    right_path: Path,
    compare_size: int,
    image_cache: dict[Path, np.ndarray],
) -> float:
    """Return a normalized pixel similarity score between two photos."""

    left_image = _load_comparison_image(left_path, compare_size, image_cache)
    right_image = _load_comparison_image(right_path, compare_size, image_cache)
    average_difference = np.mean(np.abs(left_image - right_image)) / 255.0
    return float(max(0.0, 1.0 - average_difference))


def _load_comparison_image(
    path: Path,
    compare_size: int,
    image_cache: dict[Path, np.ndarray],
) -> np.ndarray:
    """Load, normalize, resize, and cache one image for duplicate comparison."""

    cached = image_cache.get(path)
    if cached is not None:
        return cached

    register_heif_support()
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        resized = normalized.resize((compare_size, compare_size), Image.Resampling.BICUBIC)
        array = np.asarray(resized, dtype=np.float32)

    image_cache[path] = array
    return array


def _rename_surviving_members(
    day_path: Path,
    payload: dict,
    loser_relative_paths: set[str],
    settings: AppSettings,
) -> dict[str, str]:
    """Rename surviving accepted photos into stable cluster/burst-based filenames."""

    surviving_members = [
        {**member, "cluster_id": cluster["cluster_id"]}
        for cluster in payload["clusters"]
        for member in cluster["members"]
        if member["relative_path"] not in loser_relative_paths
    ]
    ordered_members = sorted(
        surviving_members,
        key=lambda member: (
            _extract_numeric_suffix(member["cluster_id"], CLUSTER_ID_PATTERN),
            _extract_numeric_suffix(member["burst_group_id"], BURST_GROUP_ID_PATTERN),
            member["captured_at"],
            member["relative_path"],
        ),
    )

    burst_sequence_by_key: dict[tuple[str, str], int] = defaultdict(int)
    rename_lookup: dict[str, str] = {}
    rename_plan: dict[Path, Path] = {}
    for member in ordered_members:
        cluster_id_number = _extract_numeric_suffix(member["cluster_id"], CLUSTER_ID_PATTERN)
        burst_group_number = _extract_numeric_suffix(member["burst_group_id"], BURST_GROUP_ID_PATTERN)
        sequence_key = (member["cluster_id"], member["burst_group_id"])
        burst_sequence_by_key[sequence_key] += 1
        sequence_number = burst_sequence_by_key[sequence_key]

        source_relative_path = Path(member["relative_path"])
        target_filename = (
            f"c{cluster_id_number:03d}_b{burst_group_number:03d}_{sequence_number:03d}"
            f"{source_relative_path.suffix}"
        )
        target_relative_path = str(Path(day_path.name) / target_filename)
        rename_lookup[member["relative_path"]] = target_relative_path

        source_path = (settings.root_path / source_relative_path).resolve()
        target_path = (day_path / target_filename).resolve()
        if source_path != target_path:
            rename_plan[source_path] = target_path

    _apply_two_phase_renames(rename_plan)
    return rename_lookup


def _apply_two_phase_renames(rename_plan: dict[Path, Path]) -> None:
    """Rename files via temporary names so swaps and cycles stay collision-safe."""

    if not rename_plan:
        return

    temporary_targets: dict[Path, Path] = {}
    for index, source_path in enumerate(sorted(rename_plan.keys(), key=str), start=1):
        temporary_path = source_path.with_name(
            f"{source_path.stem}.__cleanup_tmp_{index:03d}{source_path.suffix}"
        )
        while temporary_path.exists():
            index += 1
            temporary_path = source_path.with_name(
                f"{source_path.stem}.__cleanup_tmp_{index:03d}{source_path.suffix}"
            )

        source_path.rename(temporary_path)
        temporary_targets[temporary_path] = rename_plan[source_path]

    for temporary_path, target_path in sorted(temporary_targets.items(), key=lambda item: str(item[1])):
        if target_path.exists():
            raise RuntimeError(f"Cleanup rename target already exists: {target_path}")
        temporary_path.rename(target_path)


def _rewrite_cluster_manifest_payload(
    payload: dict,
    day_name: str,
    rename_lookup: dict[str, str],
    loser_relative_paths: set[str],
) -> dict:
    """Rewrite the manifest after duplicate rejection and survivor renaming."""

    rewritten_clusters: list[dict] = []
    surviving_members_by_burst_group: dict[str, list[dict]] = defaultdict(list)

    for cluster in payload["clusters"]:
        surviving_members = [
            member for member in cluster["members"] if member["relative_path"] not in loser_relative_paths
        ]
        if not surviving_members:
            continue

        rewritten_members = [_rewrite_member(member, rename_lookup) for member in surviving_members]
        for member in surviving_members:
            surviving_members_by_burst_group[member["burst_group_id"]].append(member)

        surviving_burst_group_ids = [
            burst_group_id
            for burst_group_id in cluster["burst_group_ids"]
            if any(member["burst_group_id"] == burst_group_id for member in rewritten_members)
        ]
        representative_member = _choose_cluster_representative_member(
            cluster["representative_filename"],
            surviving_members,
        )
        representative_filename = Path(rename_lookup[representative_member["relative_path"]]).name
        ordered_members = sorted(rewritten_members, key=lambda member: member["relative_path"])
        rewritten_clusters.append(
            {
                "cluster_id": cluster["cluster_id"],
                "representative_filename": representative_filename,
                "member_filenames": [member["filename"] for member in ordered_members],
                "burst_group_ids": surviving_burst_group_ids,
                "member_count": len(ordered_members),
                "members": ordered_members,
            }
        )

    rewritten_burst_groups = []
    for burst_group in payload["burst_groups"]:
        surviving_members = sorted(
            surviving_members_by_burst_group.get(burst_group["burst_group_id"], ()),
            key=lambda member: rename_lookup[member["relative_path"]],
        )
        if not surviving_members:
            continue
        representative_member = sorted(surviving_members, key=_duplicate_winner_sort_key)[0]
        rewritten_burst_groups.append(
            {
                "burst_group_id": burst_group["burst_group_id"],
                "representative_filename": Path(
                    rename_lookup[representative_member["relative_path"]]
                ).name,
                "member_filenames": [
                    Path(rename_lookup[member["relative_path"]]).name for member in surviving_members
                ],
                "member_count": len(surviving_members),
            }
        )

    return {
        "day_name": day_name,
        "manifest_version": payload.get("manifest_version", 1),
        "summary": {
            "accepted_photo_count": sum(cluster["member_count"] for cluster in rewritten_clusters),
            "burst_group_count": len(rewritten_burst_groups),
            "cluster_count": len(rewritten_clusters),
            "singleton_cluster_count": sum(
                1 for cluster in rewritten_clusters if cluster["member_count"] == 1
            ),
        },
        "burst_groups": rewritten_burst_groups,
        "clusters": rewritten_clusters,
        "generated_from": payload["generated_from"],
    }


def _rewrite_member(member: dict, rename_lookup: dict[str, str]) -> dict:
    """Rewrite one manifest member entry with its renamed filename and path."""

    new_relative_path = rename_lookup[member["relative_path"]]
    return {
        **member,
        "filename": Path(new_relative_path).name,
        "relative_path": new_relative_path,
    }


def _choose_cluster_representative_member(
    original_representative_filename: str,
    surviving_members: list[dict],
) -> dict:
    """Keep the original representative when possible, otherwise choose a stable fallback."""

    for member in surviving_members:
        if member["filename"] == original_representative_filename:
            return member

    return sorted(
        surviving_members,
        key=lambda member: (
            member.get("cosine_distance_to_representative", float("inf")),
            -(member.get("blur_score") or 0.0),
            member["captured_at"],
            member["relative_path"],
        ),
    )[0]


def _extract_numeric_suffix(value: str, pattern: re.Pattern[str]) -> int:
    """Extract the numeric suffix from identifiers like cluster001 or burst003."""

    match = pattern.fullmatch(value)
    if match is None:
        raise ValueError(f"Expected numbered identifier, got: {value}")
    return int(match.group(1))
