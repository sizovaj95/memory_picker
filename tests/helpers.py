"""Reusable test helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from memory_picker.models import AcceptedPhotoRecord, ClusterCategorizationResult, ImageEmbedding


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


class MockClusterCategorizer:
    """Mock Epic 4 categorizer returning deterministic cluster categories."""

    def __init__(
        self,
        categories_by_cluster_id: dict[str, str],
        rationales_by_cluster_id: dict[str, str] | None = None,
    ) -> None:
        self.categories_by_cluster_id = categories_by_cluster_id
        self.rationales_by_cluster_id = rationales_by_cluster_id or {}
        self.calls: list[tuple[str, str, str]] = []

    def categorize_cluster(self, day_name, cluster, image_path, categorization_settings) -> ClusterCategorizationResult:
        self.calls.append((day_name, cluster["cluster_id"], image_path.name))
        cluster_id = cluster["cluster_id"]
        return ClusterCategorizationResult(
            category_name=self.categories_by_cluster_id[cluster_id],
            rationale=self.rationales_by_cluster_id.get(
                cluster_id,
                f"Mock rationale for {cluster_id}",
            ),
            model_name="mock-categorizer",
            response_id=f"mock-{cluster_id}",
        )

    async def acategorize_cluster(
        self,
        day_name,
        cluster,
        image_path,
        categorization_settings,
    ) -> ClusterCategorizationResult:
        return self.categorize_cluster(day_name, cluster, image_path, categorization_settings)
