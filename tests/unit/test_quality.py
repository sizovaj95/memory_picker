"""Tests for deterministic local quality checks."""

from __future__ import annotations

from memory_picker.config import QualityThresholds
from memory_picker.models import RejectionReason
from memory_picker.quality import assess_photo
from tests.helpers import (
    write_checkerboard_image,
    write_dark_image,
    write_subject_sharp_image,
    write_text_file,
)


def test_quality_assessment_accepts_sharp_image(tmp_path):
    image_path = write_checkerboard_image(tmp_path / "sharp.jpg")

    assessment = assess_photo(image_path, QualityThresholds())

    assert assessment.is_accepted is True
    assert assessment.rejection_reasons == ()
    assert assessment.metrics.blur_score is not None


def test_quality_assessment_rejects_blurry_dark_and_corrupt_images(tmp_path):
    blurry_path = write_checkerboard_image(tmp_path / "blurry.jpg", blur_radius=10.0)
    dark_path = write_dark_image(tmp_path / "dark.jpg")
    corrupt_path = write_text_file(tmp_path / "corrupt.jpg", "not-an-image")

    blurry = assess_photo(blurry_path, QualityThresholds())
    dark = assess_photo(dark_path, QualityThresholds())
    corrupt = assess_photo(corrupt_path, QualityThresholds())

    assert RejectionReason.BLURRY in blurry.rejection_reasons
    assert RejectionReason.TOO_DARK in dark.rejection_reasons
    assert corrupt.rejection_reasons == (RejectionReason.CORRUPT,)


def test_quality_assessment_is_more_forgiving_of_intentional_background_blur(tmp_path):
    subject_sharp_path = write_subject_sharp_image(tmp_path / "subject_sharp.jpg")
    fully_blurry_path = write_checkerboard_image(tmp_path / "fully_blurry.jpg", blur_radius=10.0)
    thresholds = QualityThresholds(blur_threshold=40.0, blur_top_tile_fraction=0.25)

    subject_sharp = assess_photo(subject_sharp_path, thresholds)
    fully_blurry = assess_photo(fully_blurry_path, thresholds)

    assert subject_sharp.is_accepted is True
    assert subject_sharp.metrics.blur_score is not None
    assert fully_blurry.is_accepted is False
    assert RejectionReason.BLURRY in fully_blurry.rejection_reasons
