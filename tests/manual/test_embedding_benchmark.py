"""Optional manual benchmark for the real DINOv2 embedder."""

from __future__ import annotations

import os

import pytest

from memory_picker.config import build_settings
from memory_picker.embeddings import DinoV2ImageEmbedder
from memory_picker.preprocessing import iter_day_directories, load_day_photo_records


@pytest.mark.skipif(
    not os.environ.get("MEMORY_PICKER_BENCHMARK_ROOT"),
    reason="Set MEMORY_PICKER_BENCHMARK_ROOT to run the manual embedding benchmark.",
)
def test_dinov2_embedder_on_real_day_folder():
    root = build_settings(os.environ["MEMORY_PICKER_BENCHMARK_ROOT"]).root_path
    settings = build_settings(root)
    day_path = iter_day_directories(settings)[0]
    records = load_day_photo_records(day_path, settings)

    embedder = DinoV2ImageEmbedder(settings.embedding_settings)
    embeddings = embedder.embed_images(records[: min(4, len(records))])

    assert len(embeddings) > 0
