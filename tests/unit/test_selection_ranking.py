"""Tests for Epic 3 GPT request construction."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from memory_picker.config import SelectionSettings
from memory_picker.models import DayCandidatePhoto, FinalistCandidate
from memory_picker.selection_ranking import build_day_ranking_input, build_final_curation_input


def test_build_day_ranking_input_includes_optional_preferences(tmp_path):
    image_path = tmp_path / "a.jpg"
    image_path.write_bytes(b"fake-image")
    candidates = [
        DayCandidatePhoto(
            photo_id="day01/a.jpg",
            day_name="day01",
            source_path=image_path,
            relative_path=Path("day01/a.jpg"),
            cluster_id="cluster001",
            burst_group_id="burst001",
            captured_at=datetime(2026, 1, 1, 10, 0, 0),
        )
    ]

    request_input, prompt_name = build_day_ranking_input(
        day_name="day01",
        candidates=candidates,
        selection_settings=SelectionSettings(
            preference_prompt="Nature, people, architecture, animals, food.",
        ),
        image_inputs=[{"type": "input_image", "file_id": "file-test-123"}],
    )

    content = request_input[0]["content"]
    assert prompt_name == "default_plus_user_preferences"
    assert "Nature, people, architecture" in content[0]["text"]
    assert content[1]["text"] == "Photo ID: day01/a.jpg"
    assert content[2]["type"] == "input_image"
    assert content[2]["file_id"] == "file-test-123"
    assert "cluster001" not in content[0]["text"]


def test_build_final_curation_input_keeps_cluster_metadata_out_of_prompt(tmp_path):
    image_path = tmp_path / "a.jpg"
    image_path.write_bytes(b"fake-image")
    finalists = [
        FinalistCandidate(
            day_name="day01",
            photo_id="day01/a.jpg",
            source_path=image_path,
            relative_path=Path("day01/a.jpg"),
            cluster_id="cluster001",
            burst_group_id="burst001",
            first_pass_rank=1,
            normalized_score=0.95,
            overall_score=95.0,
            theme_tags=("people",),
            rationale="Strong photo.",
            shortlist_origin="provisional",
            provisional_selected=True,
        )
    ]

    request_input, prompt_name = build_final_curation_input(
        finalists=finalists,
        selection_settings=SelectionSettings(
            preference_prompt="Prefer group photos over nature photos.",
        ),
        image_inputs=[{"type": "input_image", "file_id": "file-test-456"}],
    )

    content = request_input[0]["content"]
    assert prompt_name == "finalist_curation_plus_user_preferences"
    assert "Prefer group photos" in content[0]["text"]
    assert "compare the shortlisted photos against each other" in content[0]["text"].lower()
    assert "cluster001" not in content[0]["text"]
    assert content[1]["text"] == "Photo ID: day01/a.jpg"
    assert content[2]["file_id"] == "file-test-456"
