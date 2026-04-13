"""Epic 3 candidate preparation and diversity-aware final selection logic."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Iterable

from memory_picker.config import AppSettings, SelectionSettings
from memory_picker.models import (
    DayCandidatePhoto,
    DayRankingRecord,
    DaySelectionResult,
    FinalCurationRecord,
    FinalistCandidate,
    PhotoSelectionDecision,
    TripSelectedPhoto,
)
from memory_picker.preprocessing import iter_day_directories

LOGGER = logging.getLogger("memory_picker.selection")


def load_cluster_manifest(day_path: Path) -> dict:
    """Load the Epic 2 cluster manifest for one day."""

    manifest_path = day_path / "cluster_manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def build_day_candidates(day_path: Path, settings: AppSettings) -> list[DayCandidatePhoto]:
    """Build one burst-deduplicated candidate per burst group from a day manifest."""

    payload = load_cluster_manifest(day_path)
    burst_representatives = {
        item["burst_group_id"]: item["representative_filename"] for item in payload["burst_groups"]
    }

    candidates: list[DayCandidatePhoto] = []
    seen_photo_ids: set[str] = set()
    for cluster in payload["clusters"]:
        members_by_burst_group: dict[str, list[dict]] = {}
        for member in cluster["members"]:
            members_by_burst_group.setdefault(member["burst_group_id"], []).append(member)

        for burst_group_id in cluster["burst_group_ids"]:
            burst_members = members_by_burst_group.get(burst_group_id, [])
            if not burst_members:
                continue
            representative_filename = burst_representatives.get(burst_group_id)
            member = next(
                (
                    burst_member
                    for burst_member in burst_members
                    if burst_member["filename"] == representative_filename
                ),
                burst_members[0],
            )

            relative_path = Path(member["relative_path"])
            photo_id = str(relative_path)
            if photo_id in seen_photo_ids:
                continue

            candidates.append(
                DayCandidatePhoto(
                    photo_id=photo_id,
                    day_name=day_path.name,
                    source_path=(settings.root_path / relative_path).resolve(),
                    relative_path=relative_path,
                    cluster_id=cluster["cluster_id"],
                    burst_group_id=member["burst_group_id"],
                    captured_at=datetime.fromisoformat(member["captured_at"]),
                    blur_score=member.get("blur_score"),
                    brightness_mean=member.get("brightness_mean"),
                    overexposed_ratio=member.get("overexposed_ratio"),
                )
            )
            seen_photo_ids.add(photo_id)

    return sorted(candidates, key=lambda item: (item.captured_at, str(item.relative_path)))


def iter_rankable_days(settings: AppSettings) -> list[Path]:
    """Return day folders that have cluster manifests and accepted photo candidates."""

    rankable_days: list[Path] = []
    for day_path in iter_day_directories(settings):
        if (day_path / "cluster_manifest.json").exists():
            rankable_days.append(day_path)
    return rankable_days


def maybe_sample_day_candidates(
    day_name: str,
    candidates: list[DayCandidatePhoto],
    selection_settings: SelectionSettings,
) -> list[DayCandidatePhoto]:
    """Optionally downsample day candidates for debug or connectivity-test runs."""

    limit = selection_settings.max_ranking_candidates_per_day
    if limit is None or len(candidates) <= limit:
        return candidates

    sampler = random.Random(f"{selection_settings.ranking_candidate_sample_seed}:{day_name}")
    sampled = sampler.sample(candidates, limit)
    return sorted(sampled, key=lambda item: (item.captured_at, str(item.relative_path)))


def compute_normalized_score(rank: int, total_count: int, overall_score: float) -> float:
    """Blend rank position and absolute score for local trip-wide comparison."""

    if total_count <= 1:
        rank_component = 1.0
    else:
        rank_component = 1.0 - ((rank - 1) / (total_count - 1))
    score_component = max(0.0, min(overall_score, 100.0)) / 100.0
    return round((0.7 * score_component) + (0.3 * rank_component), 6)


def validate_day_rankings(
    day_name: str,
    candidates: Iterable[DayCandidatePhoto],
    rankings: Iterable[DayRankingRecord],
) -> list[DayRankingRecord]:
    """Normalize malformed model output into a full deterministic ranking."""

    candidate_list = list(candidates)
    candidate_ids = {candidate.photo_id for candidate in candidate_list}
    cleaned_rankings: list[DayRankingRecord] = []
    seen_photo_ids: set[str] = set()
    dropped_duplicate_count = 0
    dropped_unexpected_count = 0

    for ranking in sorted(rankings, key=lambda item: (item.rank, item.photo_id)):
        if ranking.photo_id not in candidate_ids:
            dropped_unexpected_count += 1
            continue
        if ranking.photo_id in seen_photo_ids:
            dropped_duplicate_count += 1
            continue
        seen_photo_ids.add(ranking.photo_id)
        cleaned_rankings.append(ranking)

    missing_candidates = sorted(
        [candidate for candidate in candidate_list if candidate.photo_id not in seen_photo_ids],
        key=lambda candidate: (candidate.captured_at, str(candidate.relative_path)),
    )
    if dropped_duplicate_count or dropped_unexpected_count or missing_candidates:
        LOGGER.warning(
            "Repairing malformed ranking for %s: kept=%s missing=%s dropped_duplicates=%s dropped_unexpected=%s",
            day_name,
            len(cleaned_rankings),
            len(missing_candidates),
            dropped_duplicate_count,
            dropped_unexpected_count,
        )

    repaired_rankings: list[DayRankingRecord] = []
    total_count = len(candidate_list)
    for rank, ranking in enumerate(cleaned_rankings, start=1):
        repaired_rankings.append(
            DayRankingRecord(
                photo_id=ranking.photo_id,
                rank=rank,
                overall_score=ranking.overall_score,
                technical_quality_score=ranking.technical_quality_score,
                storytelling_score=ranking.storytelling_score,
                distinctiveness_score=ranking.distinctiveness_score,
                theme_tags=ranking.theme_tags,
                rationale=ranking.rationale,
                is_good_enough=ranking.is_good_enough,
                normalized_score=compute_normalized_score(
                    rank=rank,
                    total_count=total_count,
                    overall_score=ranking.overall_score,
                ),
            )
        )

    next_rank = len(repaired_rankings) + 1
    for candidate in missing_candidates:
        repaired_rankings.append(
            DayRankingRecord(
                photo_id=candidate.photo_id,
                rank=next_rank,
                overall_score=0.0,
                technical_quality_score=0.0,
                storytelling_score=0.0,
                distinctiveness_score=0.0,
                theme_tags=(),
                rationale="Appended after incomplete model ranking output.",
                is_good_enough=False,
                normalized_score=compute_normalized_score(
                    rank=next_rank,
                    total_count=total_count,
                    overall_score=0.0,
                ),
            )
        )
        next_rank += 1

    return repaired_rankings


def validate_final_curation_records(
    finalists: Iterable[FinalistCandidate],
    rankings: Iterable[FinalCurationRecord],
) -> list[FinalCurationRecord]:
    """Normalize malformed second-pass curation output into a full shortlist ranking."""

    finalist_list = list(finalists)
    finalist_ids = {finalist.photo_id for finalist in finalist_list}
    cleaned_rankings: list[FinalCurationRecord] = []
    seen_photo_ids: set[str] = set()
    dropped_duplicate_count = 0
    dropped_unexpected_count = 0

    for ranking in sorted(rankings, key=lambda item: (item.rank, item.photo_id)):
        if ranking.photo_id not in finalist_ids:
            dropped_unexpected_count += 1
            continue
        if ranking.photo_id in seen_photo_ids:
            dropped_duplicate_count += 1
            continue

        duplicate_of_photo_id = ranking.duplicate_of_photo_id
        if duplicate_of_photo_id not in finalist_ids or duplicate_of_photo_id == ranking.photo_id:
            duplicate_of_photo_id = None

        cleaned_rankings.append(
            FinalCurationRecord(
                photo_id=ranking.photo_id,
                rank=ranking.rank,
                keep_for_album=ranking.keep_for_album,
                duplicate_of_photo_id=duplicate_of_photo_id,
                materially_distinct_exception=ranking.materially_distinct_exception,
                rationale=ranking.rationale,
            )
        )
        seen_photo_ids.add(ranking.photo_id)

    missing_finalists = sorted(
        [finalist for finalist in finalist_list if finalist.photo_id not in seen_photo_ids],
        key=lambda finalist: (
            finalist.provisional_selected is False,
            finalist.first_pass_rank,
            finalist.day_name,
            finalist.photo_id,
        ),
    )
    if dropped_duplicate_count or dropped_unexpected_count or missing_finalists:
        LOGGER.warning(
            "Repairing malformed finalist curation: kept=%s missing=%s dropped_duplicates=%s dropped_unexpected=%s",
            len(cleaned_rankings),
            len(missing_finalists),
            dropped_duplicate_count,
            dropped_unexpected_count,
        )

    repaired: list[FinalCurationRecord] = []
    for rank, ranking in enumerate(cleaned_rankings, start=1):
        repaired.append(
            FinalCurationRecord(
                photo_id=ranking.photo_id,
                rank=rank,
                keep_for_album=ranking.keep_for_album,
                duplicate_of_photo_id=ranking.duplicate_of_photo_id,
                materially_distinct_exception=ranking.materially_distinct_exception,
                rationale=ranking.rationale,
            )
        )

    next_rank = len(repaired) + 1
    for finalist in missing_finalists:
        repaired.append(
            FinalCurationRecord(
                photo_id=finalist.photo_id,
                rank=next_rank,
                keep_for_album=False,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Appended after incomplete finalist curation output.",
            )
        )
        next_rank += 1

    return repaired


def good_enough_prefix(rankings: tuple[DayRankingRecord, ...]) -> tuple[DayRankingRecord, ...]:
    """Return the leading good-enough records before the first explicit stop."""

    accepted: list[DayRankingRecord] = []
    for ranking in rankings:
        if not ranking.is_good_enough:
            break
        accepted.append(ranking)
    return tuple(accepted)


def select_trip_photos(
    day_results: list[DaySelectionResult],
    selection_settings: SelectionSettings,
    final_curation_records: Iterable[FinalCurationRecord] | None = None,
) -> tuple[list[TripSelectedPhoto], list[DaySelectionResult], str | None]:
    """Apply cluster-aware local selection and optional second-pass curation."""

    total_cap = selection_settings.max_photos_total or float("inf")
    day_cap = selection_settings.max_photos_per_day or float("inf")

    candidate_lookup = {
        (result.day_name, candidate.photo_id): candidate
        for result in day_results
        for candidate in result.candidates
    }
    ranking_lookup = {
        (result.day_name, ranking.photo_id): ranking
        for result in day_results
        for ranking in result.rankings
    }

    provisional_selected, overflow_rankings = _build_provisional_selection(
        day_results=day_results,
        selection_settings=selection_settings,
        candidate_lookup=candidate_lookup,
        ranking_lookup=ranking_lookup,
        day_cap=day_cap,
        total_cap=total_cap,
    )
    finalists = build_finalist_shortlist(
        day_results=day_results,
        provisional_selected=provisional_selected,
        overflow_rankings=overflow_rankings,
        candidate_lookup=candidate_lookup,
        ranking_lookup=ranking_lookup,
        selection_settings=selection_settings,
    )

    decision_lookup = {
        (result.day_name, ranking.photo_id): PhotoSelectionDecision(
            day_name=result.day_name,
            photo_id=ranking.photo_id,
        )
        for result in day_results
        for ranking in result.rankings
    }

    provisional_photo_ids = {photo.photo_id for photo in provisional_selected}
    for finalist in finalists:
        key = (finalist.day_name, finalist.photo_id)
        existing = decision_lookup[key]
        decision_lookup[key] = PhotoSelectionDecision(
            day_name=existing.day_name,
            photo_id=existing.photo_id,
            provisional_selected=existing.provisional_selected or finalist.provisional_selected,
            finalist_shortlisted=True,
            shortlist_origin=finalist.shortlist_origin,
            final_curation_status=existing.final_curation_status,
            duplicate_of_photo_id=existing.duplicate_of_photo_id,
            used_cluster_exception=existing.used_cluster_exception,
            final_curation_rank=existing.final_curation_rank,
        )

    for photo in provisional_selected:
        key = (photo.day_name, photo.photo_id)
        existing = decision_lookup[key]
        decision_lookup[key] = PhotoSelectionDecision(
            day_name=existing.day_name,
            photo_id=existing.photo_id,
            provisional_selected=True,
            finalist_shortlisted=existing.finalist_shortlisted,
            shortlist_origin=existing.shortlist_origin,
            final_curation_status=existing.final_curation_status,
            duplicate_of_photo_id=existing.duplicate_of_photo_id,
            used_cluster_exception=existing.used_cluster_exception,
            final_curation_rank=existing.final_curation_rank,
        )

    curated_selected = _apply_final_curation(
        finalists=finalists,
        final_curation_records=list(final_curation_records or ()),
        decision_lookup=decision_lookup,
        selection_settings=selection_settings,
        day_cap=day_cap,
        total_cap=total_cap,
    )

    updated_day_results: list[DaySelectionResult] = []
    for result in day_results:
        updated_day_results.append(
            DaySelectionResult(
                day_name=result.day_name,
                candidates=result.candidates,
                rankings=result.rankings,
                manifest_path=result.manifest_path,
                prompt_name=result.prompt_name,
                model_name=result.model_name,
                response_id=result.response_id,
                provisional_photo_ids=tuple(
                    ranking.photo_id
                    for ranking in result.rankings
                    if ranking.photo_id in provisional_photo_ids
                ),
                finalist_photo_ids=tuple(
                    ranking.photo_id
                    for ranking in result.rankings
                    if decision_lookup[(result.day_name, ranking.photo_id)].finalist_shortlisted
                ),
                selection_decisions=tuple(
                    decision_lookup[(result.day_name, ranking.photo_id)] for ranking in result.rankings
                ),
            )
        )

    selected = sorted(curated_selected, key=lambda item: (item.day_name, item.rank, item.photo_id))
    if not selected:
        return [], updated_day_results, "No photos survived the final curation pass."

    if total_cap != float("inf") and len(selected) < int(total_cap):
        return (
            selected,
            updated_day_results,
            "Selection stopped early because no stronger curated photos remained.",
        )

    return selected, updated_day_results, None


def build_finalist_shortlist(
    day_results: list[DaySelectionResult],
    provisional_selected: list[TripSelectedPhoto],
    overflow_rankings: dict[str, tuple[DayRankingRecord, ...]],
    candidate_lookup: dict[tuple[str, str], DayCandidatePhoto],
    ranking_lookup: dict[tuple[str, str], DayRankingRecord],
    selection_settings: SelectionSettings,
) -> list[FinalistCandidate]:
    """Build the small second-pass shortlist from provisional winners and alternates."""

    finalists: list[FinalistCandidate] = []
    added_photo_ids: set[str] = set()
    provisional_by_cluster = {
        (photo.day_name, photo.cluster_id): photo for photo in provisional_selected
    }

    for photo in sorted(
        provisional_selected,
        key=lambda item: (-item.normalized_score, item.day_name, item.rank, item.photo_id),
    ):
        finalists.append(
            _build_finalist_candidate(
                photo=photo,
                shortlist_origin="provisional",
                provisional_selected=True,
            )
        )
        added_photo_ids.add(photo.photo_id)

    cluster_alternates: list[FinalistCandidate] = []
    extra_day_candidates: list[FinalistCandidate] = []
    for result in sorted(day_results, key=lambda item: item.day_name):
        strong_prefix = overflow_rankings.get(result.day_name, ())
        extra_count = 0
        for ranking in strong_prefix:
            candidate = candidate_lookup[(result.day_name, ranking.photo_id)]
            selected_for_cluster = provisional_by_cluster.get((result.day_name, candidate.cluster_id))
            if ranking.photo_id in added_photo_ids:
                continue
            if selected_for_cluster is not None and candidate.burst_group_id != selected_for_cluster.burst_group_id:
                cluster_alternates.append(
                    FinalistCandidate(
                        day_name=result.day_name,
                        photo_id=ranking.photo_id,
                        source_path=candidate.source_path,
                        relative_path=candidate.relative_path,
                        cluster_id=candidate.cluster_id,
                        burst_group_id=candidate.burst_group_id,
                        first_pass_rank=ranking.rank,
                        normalized_score=ranking.normalized_score,
                        overall_score=ranking.overall_score,
                        theme_tags=ranking.theme_tags,
                        rationale=ranking.rationale,
                        shortlist_origin="cluster_alternate",
                        provisional_selected=False,
                    )
                )
                added_photo_ids.add(ranking.photo_id)
                continue

            if (
                selection_settings.allow_spare_capacity_reuse
                and extra_count < selection_settings.second_pass_extra_candidates_per_day
            ):
                extra_day_candidates.append(
                    FinalistCandidate(
                        day_name=result.day_name,
                        photo_id=ranking.photo_id,
                        source_path=candidate.source_path,
                        relative_path=candidate.relative_path,
                        cluster_id=candidate.cluster_id,
                        burst_group_id=candidate.burst_group_id,
                        first_pass_rank=ranking.rank,
                        normalized_score=ranking.normalized_score,
                        overall_score=ranking.overall_score,
                        theme_tags=ranking.theme_tags,
                        rationale=ranking.rationale,
                        shortlist_origin="day_alternate",
                        provisional_selected=False,
                    )
                )
                added_photo_ids.add(ranking.photo_id)
                extra_count += 1

    finalists.extend(
        sorted(
            cluster_alternates,
            key=lambda item: (-item.normalized_score, item.day_name, item.first_pass_rank, item.photo_id),
        )
    )
    finalists.extend(
        sorted(
            extra_day_candidates,
            key=lambda item: (-item.normalized_score, item.day_name, item.first_pass_rank, item.photo_id),
        )
    )
    return finalists


def prepare_finalist_shortlist(
    day_results: list[DaySelectionResult],
    selection_settings: SelectionSettings,
) -> list[FinalistCandidate]:
    """Build the second-pass shortlist from saved day results."""

    candidate_lookup = {
        (result.day_name, candidate.photo_id): candidate
        for result in day_results
        for candidate in result.candidates
    }
    ranking_lookup = {
        (result.day_name, ranking.photo_id): ranking
        for result in day_results
        for ranking in result.rankings
    }
    provisional_selected, overflow_rankings = _build_provisional_selection(
        day_results=day_results,
        selection_settings=selection_settings,
        candidate_lookup=candidate_lookup,
        ranking_lookup=ranking_lookup,
        day_cap=selection_settings.max_photos_per_day or float("inf"),
        total_cap=selection_settings.max_photos_total or float("inf"),
    )
    return build_finalist_shortlist(
        day_results=day_results,
        provisional_selected=provisional_selected,
        overflow_rankings=overflow_rankings,
        candidate_lookup=candidate_lookup,
        ranking_lookup=ranking_lookup,
        selection_settings=selection_settings,
    )


def _build_finalist_candidate(
    photo: TripSelectedPhoto,
    shortlist_origin: str,
    provisional_selected: bool,
) -> FinalistCandidate:
    return FinalistCandidate(
        day_name=photo.day_name,
        photo_id=photo.photo_id,
        source_path=photo.source_path,
        relative_path=photo.relative_path,
        cluster_id=photo.cluster_id,
        burst_group_id=photo.burst_group_id,
        first_pass_rank=photo.rank,
        normalized_score=photo.normalized_score,
        overall_score=photo.overall_score,
        theme_tags=photo.theme_tags,
        rationale=photo.rationale,
        shortlist_origin=shortlist_origin,
        provisional_selected=provisional_selected,
    )


def _build_provisional_selection(
    day_results: list[DaySelectionResult],
    selection_settings: SelectionSettings,
    candidate_lookup: dict[tuple[str, str], DayCandidatePhoto],
    ranking_lookup: dict[tuple[str, str], DayRankingRecord],
    day_cap: float,
    total_cap: float,
) -> tuple[list[TripSelectedPhoto], dict[str, tuple[DayRankingRecord, ...]]]:
    provisional: list[TripSelectedPhoto] = []
    overflow_rankings: dict[str, tuple[DayRankingRecord, ...]] = {}
    total_limit = None if total_cap == float("inf") else int(total_cap)

    for result in sorted(day_results, key=lambda item: item.day_name):
        strong_prefix = good_enough_prefix(result.rankings)
        day_selected = 0
        used_clusters: set[tuple[str, str]] = set()
        overflow: list[DayRankingRecord] = []

        for ranking in strong_prefix:
            candidate = candidate_lookup[(result.day_name, ranking.photo_id)]
            cluster_key = (result.day_name, candidate.cluster_id)
            if cluster_key in used_clusters:
                overflow.append(ranking)
                continue
            if day_cap != float("inf") and day_selected >= int(day_cap):
                overflow.append(ranking)
                continue
            if total_limit is not None and len(provisional) >= total_limit:
                overflow.append(ranking)
                continue

            provisional.append(
                _build_trip_selected_record(
                    day_name=result.day_name,
                    ranking=ranking,
                    candidate_lookup=candidate_lookup,
                    shortlist_origin="provisional",
                    provisional_selected=True,
                )
            )
            used_clusters.add(cluster_key)
            day_selected += 1

        overflow.extend(
            ranking
            for ranking in strong_prefix
            if ranking.photo_id not in {photo.photo_id for photo in provisional if photo.day_name == result.day_name}
            and ranking not in overflow
        )
        overflow_rankings[result.day_name] = tuple(
            sorted(overflow, key=lambda item: (item.rank, item.photo_id))
        )

    return provisional, overflow_rankings


def _apply_final_curation(
    finalists: list[FinalistCandidate],
    final_curation_records: list[FinalCurationRecord],
    decision_lookup: dict[tuple[str, str], PhotoSelectionDecision],
    selection_settings: SelectionSettings,
    day_cap: float,
    total_cap: float,
) -> list[TripSelectedPhoto]:
    if not finalists:
        return []

    finalist_by_photo_id = {finalist.photo_id: finalist for finalist in finalists}
    if final_curation_records:
        applied_rankings = validate_final_curation_records(finalists, final_curation_records)
    else:
        applied_rankings = [
            FinalCurationRecord(
                photo_id=finalist.photo_id,
                rank=index,
                keep_for_album=True,
                duplicate_of_photo_id=None,
                materially_distinct_exception=False,
                rationale="Accepted from first-pass shortlist without second-pass curation.",
            )
            for index, finalist in enumerate(finalists, start=1)
        ]

    selected: list[TripSelectedPhoto] = []
    kept_photo_ids: set[str] = set()
    day_counts: dict[str, int] = {}
    cluster_selections: dict[tuple[str, str], list[FinalistCandidate]] = {}
    total_limit = None if total_cap == float("inf") else int(total_cap)

    for record in applied_rankings:
        finalist = finalist_by_photo_id[record.photo_id]
        key = (finalist.day_name, finalist.photo_id)
        decision = decision_lookup[key]
        decision = PhotoSelectionDecision(
            day_name=decision.day_name,
            photo_id=decision.photo_id,
            provisional_selected=decision.provisional_selected,
            finalist_shortlisted=decision.finalist_shortlisted,
            shortlist_origin=decision.shortlist_origin,
            final_curation_status=decision.final_curation_status,
            duplicate_of_photo_id=record.duplicate_of_photo_id,
            used_cluster_exception=decision.used_cluster_exception,
            final_curation_rank=record.rank,
        )

        if not record.keep_for_album:
            decision_lookup[key] = _updated_decision(
                decision,
                final_curation_status="rejected_by_second_pass",
            )
            continue

        if record.duplicate_of_photo_id and record.duplicate_of_photo_id in kept_photo_ids:
            decision_lookup[key] = _updated_decision(
                decision,
                final_curation_status="duplicate_rejected",
            )
            continue

        if day_cap != float("inf") and day_counts.get(finalist.day_name, 0) >= int(day_cap):
            decision_lookup[key] = _updated_decision(
                decision,
                final_curation_status="rejected_by_day_cap",
            )
            continue

        if total_limit is not None and len(selected) >= total_limit:
            decision_lookup[key] = _updated_decision(
                decision,
                final_curation_status="rejected_by_total_cap",
            )
            continue

        cluster_key = (finalist.day_name, finalist.cluster_id)
        existing_cluster_members = cluster_selections.get(cluster_key, [])
        used_cluster_exception = False
        if existing_cluster_members:
            if len(existing_cluster_members) >= selection_settings.max_final_photos_per_cluster_with_exception:
                decision_lookup[key] = _updated_decision(
                    decision,
                    final_curation_status="rejected_by_cluster_cap",
                )
                continue
            if len(existing_cluster_members) >= selection_settings.max_final_photos_per_cluster:
                existing_bursts = {item.burst_group_id for item in existing_cluster_members}
                if (
                    not record.materially_distinct_exception
                    or finalist.burst_group_id in existing_bursts
                ):
                    decision_lookup[key] = _updated_decision(
                        decision,
                        final_curation_status="rejected_by_cluster_cap",
                    )
                    continue
                used_cluster_exception = True

        selected.append(
            TripSelectedPhoto(
                day_name=finalist.day_name,
                photo_id=finalist.photo_id,
                source_path=finalist.source_path,
                relative_path=finalist.relative_path,
                cluster_id=finalist.cluster_id,
                burst_group_id=finalist.burst_group_id,
                rank=finalist.first_pass_rank,
                normalized_score=finalist.normalized_score,
                overall_score=finalist.overall_score,
                theme_tags=finalist.theme_tags,
                rationale=record.rationale or finalist.rationale,
                shortlist_origin=finalist.shortlist_origin,
                provisional_selected=finalist.provisional_selected,
                used_cluster_exception=used_cluster_exception,
                final_curation_rank=record.rank,
            )
        )
        kept_photo_ids.add(finalist.photo_id)
        cluster_selections.setdefault(cluster_key, []).append(finalist)
        day_counts[finalist.day_name] = day_counts.get(finalist.day_name, 0) + 1
        decision_lookup[key] = _updated_decision(
            decision,
            final_curation_status="selected",
            used_cluster_exception=used_cluster_exception,
        )

    return selected


def _build_trip_selected_record(
    day_name: str,
    ranking: DayRankingRecord,
    candidate_lookup: dict[tuple[str, str], DayCandidatePhoto],
    shortlist_origin: str,
    provisional_selected: bool,
) -> TripSelectedPhoto:
    candidate = candidate_lookup[(day_name, ranking.photo_id)]
    return TripSelectedPhoto(
        day_name=day_name,
        photo_id=ranking.photo_id,
        source_path=candidate.source_path,
        relative_path=candidate.relative_path,
        cluster_id=candidate.cluster_id,
        burst_group_id=candidate.burst_group_id,
        rank=ranking.rank,
        normalized_score=ranking.normalized_score,
        overall_score=ranking.overall_score,
        theme_tags=ranking.theme_tags,
        rationale=ranking.rationale,
        shortlist_origin=shortlist_origin,
        provisional_selected=provisional_selected,
    )


def _updated_decision(
    decision: PhotoSelectionDecision,
    *,
    final_curation_status: str,
    used_cluster_exception: bool | None = None,
) -> PhotoSelectionDecision:
    return PhotoSelectionDecision(
        day_name=decision.day_name,
        photo_id=decision.photo_id,
        provisional_selected=decision.provisional_selected,
        finalist_shortlisted=decision.finalist_shortlisted,
        shortlist_origin=decision.shortlist_origin,
        final_curation_status=final_curation_status,
        duplicate_of_photo_id=decision.duplicate_of_photo_id,
        used_cluster_exception=(
            decision.used_cluster_exception
            if used_cluster_exception is None
            else used_cluster_exception
        ),
        final_curation_rank=decision.final_curation_rank,
    )
