"""Reusable test helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


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
