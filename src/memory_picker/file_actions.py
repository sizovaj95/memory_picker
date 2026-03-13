"""Filesystem actions for accepted, rejected, and non-photo files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from memory_picker.config import AppSettings
from memory_picker.models import DestinationCategory, FileActionSummary, FileMovePlan

LOGGER = logging.getLogger("memory_picker.file_actions")


def build_destination_path(settings: AppSettings, plan: FileMovePlan) -> Path:
    """Return the destination path for a move plan."""

    day_root = settings.root_path / plan.day_name
    if plan.destination_category == DestinationCategory.ACCEPTED:
        return day_root / plan.source_path.name
    if plan.destination_category == DestinationCategory.REJECTED:
        return day_root / settings.managed_folders.rejected / plan.source_path.name
    return day_root / settings.managed_folders.not_photo / plan.source_path.name


def resolve_collision(target_path: Path, settings: AppSettings) -> Path:
    """Return a collision-safe destination path."""

    if not target_path.exists():
        return target_path

    counter = 1
    while True:
        candidate = target_path.with_name(
            f"{target_path.stem}{settings.collision_suffix_separator}{counter:02d}"
            f"{target_path.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1


def apply_move_plans(settings: AppSettings, move_plans: list[FileMovePlan]) -> FileActionSummary:
    """Execute planned filesystem moves safely and deterministically."""

    created_directories: set[Path] = set()
    moved_paths: list[Path] = []
    accepted_moved = 0
    rejected_moved = 0
    artifacts_moved = 0

    ordered_plans = sorted(
        move_plans,
        key=lambda plan: (plan.day_name, plan.destination_category.value, plan.source_path.name.lower()),
    )

    for plan in ordered_plans:
        if not plan.source_path.exists():
            LOGGER.warning("Skipping missing source path: %s", plan.source_path)
            continue

        destination_path = build_destination_path(settings, plan)
        destination_dir = destination_path.parent
        if not destination_dir.exists():
            destination_dir.mkdir(parents=True, exist_ok=True)
            created_directories.add(destination_dir)

        safe_destination = resolve_collision(destination_path, settings)
        if plan.source_path.resolve() == safe_destination.resolve():
            continue

        shutil.move(str(plan.source_path), str(safe_destination))
        moved_paths.append(safe_destination)

        if plan.destination_category == DestinationCategory.ACCEPTED:
            accepted_moved += 1
        elif plan.destination_category == DestinationCategory.REJECTED:
            rejected_moved += 1
        else:
            artifacts_moved += 1

    return FileActionSummary(
        accepted_moved=accepted_moved,
        rejected_moved=rejected_moved,
        artifacts_moved=artifacts_moved,
        created_directories=len(created_directories),
        moved_paths=tuple(moved_paths),
    )
