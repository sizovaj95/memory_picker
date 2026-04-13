"""Tests for Epic 3 candidate prep and diversity-aware final selection."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from memory_picker.config import SelectionSettings, build_settings
from memory_picker.models import (
    DayCandidatePhoto,
    DayRankingRecord,
    DaySelectionResult,
    FinalCurationRecord,
)
from memory_picker.selection import (
    build_day_candidates,
    maybe_sample_day_candidates,
    prepare_finalist_shortlist,
    select_trip_photos,
    validate_day_rankings,
)


def test_build_day_candidates_deduplicates_every_cluster_by_burst_group(tmp_path):
    root = tmp_path / "trip"
    day_path = root / "day01"
    day_path.mkdir(parents=True)

    manifest = {
        "burst_groups": [
            {
                "burst_group_id": "burst001",
                "representative_filename": "a.jpg",
            },
            {
                "burst_group_id": "burst002",
                "representative_filename": "c.jpg",
            },
            {
                "burst_group_id": "burst003",
                "representative_filename": "small_1.jpg",
            },
        ],
        "clusters": [
            {
                "cluster_id": "cluster001",
                "member_count": 6,
                "burst_group_ids": ["burst001", "burst002"],
                "members": [
                    {
                        "filename": "a.jpg",
                        "relative_path": "day01/a.jpg",
                        "burst_group_id": "burst001",
                        "captured_at": "2026-01-01T10:00:00",
                    },
                    {
                        "filename": "b.jpg",
                        "relative_path": "day01/b.jpg",
                        "burst_group_id": "burst001",
                        "captured_at": "2026-01-01T10:00:01",
                    },
                    {
                        "filename": "c.jpg",
                        "relative_path": "day01/c.jpg",
                        "burst_group_id": "burst002",
                        "captured_at": "2026-01-01T10:00:02",
                    },
                ],
            },
            {
                "cluster_id": "cluster002",
                "member_count": 2,
                "burst_group_ids": ["burst003"],
                "members": [
                    {
                        "filename": "small_1.jpg",
                        "relative_path": "day01/small_1.jpg",
                        "burst_group_id": "burst003",
                        "captured_at": "2026-01-01T11:00:00",
                    },
                    {
                        "filename": "small_2.jpg",
                        "relative_path": "day01/small_2.jpg",
                        "burst_group_id": "burst003",
                        "captured_at": "2026-01-01T11:00:01",
                    },
                ],
            },
        ],
    }
    (day_path / "cluster_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    settings = build_settings(root)
    candidates = build_day_candidates(day_path, settings)

    assert [candidate.photo_id for candidate in candidates] == [
        "day01/a.jpg",
        "day01/c.jpg",
        "day01/small_1.jpg",
    ]


def test_select_trip_photos_collapses_repeated_clusters_by_default(tmp_path):
    day_results = [
        _build_day_result(
            tmp_path=tmp_path,
            day_name="day01",
            ordered_specs=[
                ("a.jpg", "cluster001", "burst001", 96.0, True),
                ("b.jpg", "cluster001", "burst002", 95.0, True),
                ("c.jpg", "cluster002", "burst003", 92.0, True),
            ],
        )
    ]

    selected, updated_results, reason = select_trip_photos(
        day_results=day_results,
        selection_settings=SelectionSettings(
            max_photos_per_day=3,
            max_photos_total=3,
        ),
        final_curation_records=[
            FinalCurationRecord(
                photo_id="day01/a.jpg",
                rank=1,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Keep strongest repeated-scene image.",
            ),
            FinalCurationRecord(
                photo_id="day01/b.jpg",
                rank=2,
                keep_for_album=True,
                duplicate_of_photo_id="day01/a.jpg",
                materially_distinct_exception=False,
                rationale="Duplicate scene.",
            ),
            FinalCurationRecord(
                photo_id="day01/c.jpg",
                rank=3,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Different scene.",
            ),
        ],
    )

    assert [photo.photo_id for photo in selected] == ["day01/a.jpg", "day01/c.jpg"]
    decisions = {decision.photo_id: decision for decision in updated_results[0].selection_decisions}
    assert decisions["day01/b.jpg"].final_curation_status == "duplicate_rejected"
    assert reason == "Selection stopped early because no stronger curated photos remained."


def test_select_trip_photos_allows_second_cluster_photo_only_with_exception(tmp_path):
    day_results = [
        _build_day_result(
            tmp_path=tmp_path,
            day_name="day01",
            ordered_specs=[
                ("a.jpg", "cluster001", "burst001", 97.0, True),
                ("b.jpg", "cluster001", "burst002", 95.0, True),
            ],
        )
    ]

    selected, updated_results, _ = select_trip_photos(
        day_results=day_results,
        selection_settings=SelectionSettings(
            max_photos_per_day=3,
            max_photos_total=3,
            max_final_photos_per_cluster=1,
            max_final_photos_per_cluster_with_exception=2,
        ),
        final_curation_records=[
            FinalCurationRecord(
                photo_id="day01/a.jpg",
                rank=1,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Primary keeper.",
            ),
            FinalCurationRecord(
                photo_id="day01/b.jpg",
                rank=2,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=True,
                rationale="Distinct enough to keep as exception.",
            ),
        ],
    )

    assert [photo.photo_id for photo in selected] == ["day01/a.jpg", "day01/b.jpg"]
    assert selected[1].used_cluster_exception is True
    decisions = {decision.photo_id: decision for decision in updated_results[0].selection_decisions}
    assert decisions["day01/b.jpg"].used_cluster_exception is True


def test_select_trip_photos_refills_from_day_alternates_after_duplicate_removal(tmp_path):
    day_results = [
        _build_day_result(
            tmp_path=tmp_path,
            day_name="day01",
            ordered_specs=[
                ("a.jpg", "cluster001", "burst001", 98.0, True),
                ("b.jpg", "cluster001", "burst002", 96.0, True),
                ("c.jpg", "cluster002", "burst003", 94.0, True),
                ("d.jpg", "cluster003", "burst004", 91.0, True),
            ],
        )
    ]

    finalists = prepare_finalist_shortlist(
        day_results=day_results,
        selection_settings=SelectionSettings(
            max_photos_per_day=2,
            max_photos_total=3,
            second_pass_extra_candidates_per_day=2,
        ),
    )
    assert [item.photo_id for item in finalists] == [
        "day01/a.jpg",
        "day01/c.jpg",
        "day01/b.jpg",
        "day01/d.jpg",
    ]

    selected, updated_results, _ = select_trip_photos(
        day_results=day_results,
        selection_settings=SelectionSettings(
            max_photos_per_day=2,
            max_photos_total=3,
            second_pass_extra_candidates_per_day=2,
        ),
        final_curation_records=[
            FinalCurationRecord(
                photo_id="day01/a.jpg",
                rank=1,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Keep.",
            ),
            FinalCurationRecord(
                photo_id="day01/c.jpg",
                rank=2,
                keep_for_album=False,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Remove.",
            ),
            FinalCurationRecord(
                photo_id="day01/b.jpg",
                rank=3,
                keep_for_album=False,
                duplicate_of_photo_id="day01/a.jpg",
                materially_distinct_exception=False,
                rationale="Duplicate.",
            ),
            FinalCurationRecord(
                photo_id="day01/d.jpg",
                rank=4,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Fill gap.",
            ),
        ],
    )

    assert [photo.photo_id for photo in selected] == ["day01/a.jpg", "day01/d.jpg"]
    decisions = {decision.photo_id: decision for decision in updated_results[0].selection_decisions}
    assert decisions["day01/c.jpg"].final_curation_status == "rejected_by_second_pass"
    assert decisions["day01/d.jpg"].shortlist_origin == "day_alternate"


def test_maybe_sample_day_candidates_uses_configured_limit(tmp_path):
    candidates = [
        DayCandidatePhoto(
            photo_id=f"day01/{index}.jpg",
            day_name="day01",
            source_path=tmp_path / f"{index}.jpg",
            relative_path=Path("day01") / f"{index}.jpg",
            cluster_id=f"cluster{index:03d}",
            burst_group_id=f"burst{index:03d}",
            captured_at=datetime(2026, 1, 1, 10, index, 0),
        )
        for index in range(10)
    ]

    sampled = maybe_sample_day_candidates(
        day_name="day01",
        candidates=candidates,
        selection_settings=SelectionSettings(
            max_ranking_candidates_per_day=5,
            ranking_candidate_sample_seed=123,
        ),
    )

    assert len(sampled) == 5
    assert sampled == maybe_sample_day_candidates(
        day_name="day01",
        candidates=candidates,
        selection_settings=SelectionSettings(
            max_ranking_candidates_per_day=5,
            ranking_candidate_sample_seed=123,
        ),
    )


def test_validate_day_rankings_repairs_partial_rankings(tmp_path):
    candidates = [
        DayCandidatePhoto(
            photo_id=f"day01/{index}.jpg",
            day_name="day01",
            source_path=tmp_path / f"{index}.jpg",
            relative_path=Path("day01") / f"{index}.jpg",
            cluster_id=f"cluster{index:03d}",
            burst_group_id=f"burst{index:03d}",
            captured_at=datetime(2026, 1, 1, 10, index, 0),
        )
        for index in range(3)
    ]
    partial_rankings = [
        DayRankingRecord(
            photo_id="day01/1.jpg",
            rank=2,
            overall_score=88.0,
            technical_quality_score=87.0,
            storytelling_score=89.0,
            distinctiveness_score=84.0,
            theme_tags=("people",),
            rationale="Strong image.",
            is_good_enough=True,
            normalized_score=0.5,
        )
    ]

    repaired = validate_day_rankings("day01", candidates, partial_rankings)

    assert [ranking.photo_id for ranking in repaired] == [
        "day01/1.jpg",
        "day01/0.jpg",
        "day01/2.jpg",
    ]
    assert repaired[-1].is_good_enough is False
    assert repaired[-1].overall_score == 0.0


def _build_day_result(
    tmp_path: Path,
    day_name: str,
    ordered_specs: list[tuple[str, str, str, float, bool]],
) -> DaySelectionResult:
    candidates: list[DayCandidatePhoto] = []
    rankings: list[DayRankingRecord] = []
    for rank, (filename, cluster_id, burst_group_id, overall_score, is_good_enough) in enumerate(
        ordered_specs,
        start=1,
    ):
        photo_id = f"{day_name}/{filename}"
        candidates.append(
            DayCandidatePhoto(
                photo_id=photo_id,
                day_name=day_name,
                source_path=tmp_path / filename,
                relative_path=Path(day_name) / filename,
                cluster_id=cluster_id,
                burst_group_id=burst_group_id,
                captured_at=datetime(2026, 1, 1, 10, rank, 0),
            )
        )
        rankings.append(
            DayRankingRecord(
                photo_id=photo_id,
                rank=rank,
                overall_score=overall_score,
                technical_quality_score=min(overall_score + 1.0, 100.0),
                storytelling_score=overall_score,
                distinctiveness_score=max(overall_score - 2.0, 0.0),
                theme_tags=("mock",),
                rationale=f"Ranking for {photo_id}",
                is_good_enough=is_good_enough,
                normalized_score=overall_score / 100.0,
            )
        )

    return DaySelectionResult(
        day_name=day_name,
        candidates=tuple(candidates),
        rankings=tuple(rankings),
        manifest_path=tmp_path / f"{day_name}.json",
        prompt_name="mock",
        model_name="mock",
    )
