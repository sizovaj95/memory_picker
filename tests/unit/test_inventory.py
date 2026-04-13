"""Tests for trip-root inventory scanning."""

from __future__ import annotations

from memory_picker.config import build_settings
from memory_picker.inventory import scan_trip_root
from memory_picker.models import MediaClassification


def test_scan_trip_root_classifies_files_and_skips_managed_directories(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()

    (root / "photo.JPG").write_bytes(b"jpg")
    (root / "clip.MOV").write_bytes(b"mov")
    (root / "sidecar.AAE").write_text("xml", encoding="utf-8")
    (root / "unknown.bin").write_bytes(b"bin")
    (root / "day01").mkdir()
    (root / "day01" / "nested.JPG").write_bytes(b"nested")
    (root / "to_print").mkdir()
    (root / "intermediate_clusters").mkdir()
    (root / "intermediate_result").mkdir()

    inventory = scan_trip_root(build_settings(root))
    classifications = {item.source_path.name: item.classification for item in inventory}

    assert classifications == {
        "clip.MOV": MediaClassification.NON_PHOTO,
        "photo.JPG": MediaClassification.PHOTO,
        "sidecar.AAE": MediaClassification.NON_PHOTO,
        "unknown.bin": MediaClassification.UNSUPPORTED,
    }


def test_scan_trip_root_returns_absolute_paths(tmp_path):
    root = tmp_path / "trip"
    root.mkdir()
    file_path = root / "image.png"
    file_path.write_bytes(b"png")

    inventory = scan_trip_root(build_settings(root))

    assert inventory[0].source_path.is_absolute()
    assert inventory[0].size_bytes == 3
