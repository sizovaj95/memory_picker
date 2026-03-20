"""Deterministic local image quality checks."""

from __future__ import annotations

import numpy as np
from PIL import Image, UnidentifiedImageError

from memory_picker.config import QualityThresholds
from memory_picker.image_support import register_heif_support
from memory_picker.models import QualityAssessment, QualityMetrics, RejectionReason


def compute_laplacian_variance(grayscale: np.ndarray) -> float:
    """Approximate local sharpness using variance of a discrete Laplacian."""

    if grayscale.shape[0] < 3 or grayscale.shape[1] < 3:
        return 0.0

    laplacian = (
        grayscale[:-2, 1:-1]
        + grayscale[2:, 1:-1]
        + grayscale[1:-1, :-2]
        + grayscale[1:-1, 2:]
        - (4.0 * grayscale[1:-1, 1:-1])
    )
    return float(laplacian.var())


def compute_blur_score(grayscale: np.ndarray, thresholds: QualityThresholds) -> float:
    """Score blur from the sharpest tiles instead of the whole frame.

    This is intentionally more forgiving of portraits or other shots where the
    main subject is sharp but the background is soft by design.
    """

    row_tiles = np.array_split(grayscale, thresholds.blur_tile_rows, axis=0)
    tile_scores: list[float] = []

    for row_tile in row_tiles:
        for tile in np.array_split(row_tile, thresholds.blur_tile_cols, axis=1):
            tile_scores.append(compute_laplacian_variance(tile))

    if not tile_scores:
        return 0.0

    sorted_scores = np.sort(np.asarray(tile_scores, dtype=np.float32))
    top_tile_count = max(
        1,
        int(np.ceil(len(sorted_scores) * thresholds.blur_top_tile_fraction)),
    )
    return float(sorted_scores[-top_tile_count:].mean())


def assess_photo(path, thresholds: QualityThresholds) -> QualityAssessment:
    """Assess whether a photo is acceptable for downstream processing."""

    register_heif_support()
    try:
        with Image.open(path) as image:
            grayscale = np.asarray(image.convert("L"), dtype=np.float32)
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as exc:
        return QualityAssessment(
            source_path=path,
            is_accepted=False,
            rejection_reasons=(RejectionReason.CORRUPT,),
            details=str(exc),
        )

    blur_score = compute_blur_score(grayscale, thresholds)
    brightness_mean = float(grayscale.mean())
    overexposed_ratio = float(
        (grayscale >= thresholds.overexposed_pixel_threshold).mean()
    )

    rejection_reasons: list[RejectionReason] = []
    if blur_score < thresholds.blur_threshold:
        rejection_reasons.append(RejectionReason.BLURRY)
    if brightness_mean < thresholds.dark_brightness_threshold:
        rejection_reasons.append(RejectionReason.TOO_DARK)
    if overexposed_ratio > thresholds.overexposed_ratio_threshold:
        rejection_reasons.append(RejectionReason.TOO_BRIGHT)

    return QualityAssessment(
        source_path=path,
        is_accepted=not rejection_reasons,
        rejection_reasons=tuple(rejection_reasons),
        metrics=QualityMetrics(
            blur_score=blur_score,
            brightness_mean=brightness_mean,
            overexposed_ratio=overexposed_ratio,
        ),
    )
