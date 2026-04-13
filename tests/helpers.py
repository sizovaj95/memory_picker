"""Reusable test helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from memory_picker.models import (
    AcceptedPhotoRecord,
    DayRankingBatch,
    DayRankingRecord,
    FinalCurationBatch,
    FinalCurationRecord,
    ImageEmbedding,
)


def write_checkerboard_image(
    path: Path,
    capture_datetime: datetime | None = None,
    blur_radius: float = 0.0,
    size: tuple[int, int] = (128, 128),
) -> Path:
    """Create a high-contrast test image, optionally blurred."""

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    square_size = 16

    for top in range(0, size[1], square_size):
        for left in range(0, size[0], square_size):
            fill = "black" if ((left // square_size) + (top // square_size)) % 2 == 0 else "white"
            draw.rectangle(
                [left, top, left + square_size - 1, top + square_size - 1],
                fill=fill,
            )

    if blur_radius:
        image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    exif = None
    if capture_datetime is not None:
        exif = Image.Exif()
        exif[36867] = capture_datetime.strftime("%Y:%m:%d %H:%M:%S")

    if exif is not None:
        image.save(path, exif=exif)
    else:
        image.save(path)
    return path


def write_dark_image(path: Path, size: tuple[int, int] = (128, 128)) -> Path:
    """Create a dark image to trigger exposure rejection."""

    image = Image.new("RGB", size, (5, 5, 5))
    image.save(path)
    return path


def write_color_block_image(
    path: Path,
    color: tuple[int, int, int],
    size: tuple[int, int] = (128, 128),
) -> Path:
    """Create a solid-color image for deterministic histogram differences."""

    image = Image.new("RGB", size, color)
    image.save(path)
    return path


def write_subject_sharp_image(path: Path, size: tuple[int, int] = (128, 128)) -> Path:
    """Create an image with a sharp center and intentionally blurred background."""

    base = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(base)
    square_size = 16

    for top in range(0, size[1], square_size):
        for left in range(0, size[0], square_size):
            fill = "black" if ((left // square_size) + (top // square_size)) % 2 == 0 else "white"
            draw.rectangle(
                [left, top, left + square_size - 1, top + square_size - 1],
                fill=fill,
            )

    blurred = base.filter(ImageFilter.GaussianBlur(radius=10.0))
    subject_box = (
        size[0] // 4,
        size[1] // 4,
        (size[0] * 3) // 4,
        (size[1] * 3) // 4,
    )
    subject_crop = base.crop(subject_box)
    blurred.paste(subject_crop, subject_box)
    blurred.save(path)
    return path


def write_text_file(path: Path, contents: str = "placeholder") -> Path:
    """Create a text-based placeholder file."""

    path.write_text(contents, encoding="utf-8")
    return path


def set_mtime(path: Path, when: datetime) -> None:
    """Set the filesystem modification time for a file."""

    import os

    timestamp = when.timestamp()
    path.touch(exist_ok=True)
    path.chmod(0o644)
    os.utime(path, (timestamp, timestamp))


def normalize_vector(values: list[float]) -> np.ndarray:
    """Return a normalized float32 vector."""

    vector = np.asarray(values, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


class FilenameMockEmbedder:
    """Mock embedder that returns vectors by filename."""

    def __init__(self, vectors_by_filename: dict[str, list[float]]) -> None:
        self.vectors_by_filename = vectors_by_filename

    def embed_images(self, photo_records: list[AcceptedPhotoRecord]) -> list[ImageEmbedding]:
        return [
            ImageEmbedding(
                source_path=record.source_path,
                vector=normalize_vector(self.vectors_by_filename[record.source_path.name]),
            )
            for record in photo_records
        ]


class MockDayRanker:
    """Mock Epic 3 ranker returning deterministic per-day rankings."""

    def __init__(
        self,
        day_orders: dict[str, list[str]] | None = None,
        good_enough_cutoffs: dict[str, int] | None = None,
        scores_by_photo_id: dict[str, float] | None = None,
        finalist_order: list[str] | None = None,
        finalist_keep_map: dict[str, bool] | None = None,
        finalist_duplicates: dict[str, str | None] | None = None,
        finalist_exception_map: dict[str, bool] | None = None,
    ) -> None:
        self.day_orders = day_orders or {}
        self.good_enough_cutoffs = good_enough_cutoffs or {}
        self.scores_by_photo_id = scores_by_photo_id or {}
        self.finalist_order = finalist_order or []
        self.finalist_keep_map = finalist_keep_map or {}
        self.finalist_duplicates = finalist_duplicates or {}
        self.finalist_exception_map = finalist_exception_map or {}

    def rank_day(self, day_name, candidates, selection_settings) -> DayRankingBatch:
        ordered_ids = self.day_orders.get(day_name) or [candidate.photo_id for candidate in candidates]
        candidates_by_id = {candidate.photo_id: candidate for candidate in candidates}
        rankings: list[DayRankingRecord] = []
        good_enough_cutoff = self.good_enough_cutoffs.get(day_name, len(ordered_ids))

        for rank, photo_id in enumerate(ordered_ids, start=1):
            candidate = candidates_by_id[photo_id]
            overall_score = self.scores_by_photo_id.get(photo_id, max(100.0 - (rank * 5.0), 1.0))
            rankings.append(
                DayRankingRecord(
                    photo_id=candidate.photo_id,
                    rank=rank,
                    overall_score=overall_score,
                    technical_quality_score=min(overall_score + 2.0, 100.0),
                    storytelling_score=overall_score,
                    distinctiveness_score=max(overall_score - 3.0, 0.0),
                    theme_tags=("mock", candidate.day_name),
                    rationale=f"Mock ranking for {candidate.photo_id}",
                    is_good_enough=rank <= good_enough_cutoff,
                    normalized_score=0.0,
                )
            )

        normalized_rankings = [
            DayRankingRecord(
                photo_id=ranking.photo_id,
                rank=ranking.rank,
                overall_score=ranking.overall_score,
                technical_quality_score=ranking.technical_quality_score,
                storytelling_score=ranking.storytelling_score,
                distinctiveness_score=ranking.distinctiveness_score,
                theme_tags=ranking.theme_tags,
                rationale=ranking.rationale,
                is_good_enough=ranking.is_good_enough,
                normalized_score=max(0.0, min(ranking.overall_score / 100.0, 1.0)),
            )
            for ranking in rankings
        ]

        return DayRankingBatch(
            day_name=day_name,
            rankings=tuple(normalized_rankings),
            prompt_name="mock_prompt",
            model_name="mock-model",
            response_id=f"mock-{day_name}",
        )

    def curate_finalists(self, finalists, selection_settings) -> FinalCurationBatch:
        ordered_ids = self.finalist_order or [finalist.photo_id for finalist in finalists]
        rankings: list[FinalCurationRecord] = []
        for rank, photo_id in enumerate(ordered_ids, start=1):
            rankings.append(
                FinalCurationRecord(
                    photo_id=photo_id,
                    rank=rank,
                    keep_for_album=self.finalist_keep_map.get(photo_id, True),
                    duplicate_of_photo_id=self.finalist_duplicates.get(photo_id),
                    materially_distinct_exception=self.finalist_exception_map.get(photo_id, False),
                    rationale=f"Mock finalist curation for {photo_id}",
                )
            )
        return FinalCurationBatch(
            rankings=tuple(rankings),
            prompt_name="mock_finalist_prompt",
            model_name="mock-model",
            response_id="mock-finalists",
        )
