"""Epic 3 GPT-backed ranking and shortlist curation."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Protocol

from PIL import Image

from memory_picker.config import SelectionSettings
from memory_picker.models import (
    DayCandidatePhoto,
    DayRankingBatch,
    DayRankingRecord,
    FinalCurationBatch,
    FinalCurationRecord,
    FinalistCandidate,
)
from memory_picker.selection import (
    compute_normalized_score,
    validate_day_rankings,
    validate_final_curation_records,
)

try:
    from openai import APIConnectionError, OpenAI
except ImportError:  # pragma: no cover - exercised in runtime environments without the dep.
    OpenAI = None
    APIConnectionError = Exception


DEFAULT_PROMPT_NAME = "default_diversity_first"
SECOND_PASS_PROMPT_NAME = "finalist_curation"

DEFAULT_RANKING_PROMPT = """
You are selecting photos for a high-quality travel album.

Rank every photo from strongest to weakest for final inclusion.
Prefer photos that are visually strong, tell the story of the day well, and add variety to the album.
Avoid overvaluing repetitive shots or weak photos just to fill capacity.

Mark is_good_enough as true only when the photo is genuinely strong enough to deserve album consideration.
The ranking must cover every provided photo exactly once.
Use the provided photo_id values exactly as written.
Keep each rationale short: one sentence, maximum 18 words.
""".strip()

FINALIST_CURATION_PROMPT = """
You are curating the final shortlist for a travel album.

Compare the shortlisted photos against each other, not in isolation.
Avoid repeated scenes unless a second photo clearly adds different album value.
If two photos feel near-duplicate, keep the stronger one and mark the weaker duplicate_of_photo_id.
Only set materially_distinct_exception=true when two repeated-scene photos both deserve inclusion.
The ranking must cover every provided photo exactly once.
Use the provided photo_id values exactly as written.
Keep each rationale short: one sentence, maximum 18 words.
""".strip()


class DayPhotoRanker(Protocol):
    """Interface for GPT-backed ranking and shortlist curation backends."""

    def rank_day(
        self,
        day_name: str,
        candidates: list[DayCandidatePhoto],
        selection_settings: SelectionSettings,
    ) -> DayRankingBatch:
        """Rank every provided day candidate exactly once."""

    def curate_finalists(
        self,
        finalists: list[FinalistCandidate],
        selection_settings: SelectionSettings,
    ) -> FinalCurationBatch:
        """Compare a small finalist shortlist against itself for duplicate control."""


def build_day_ranking_schema() -> dict:
    """Return the strict JSON schema for one day-ranking response."""

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "day_name": {"type": "string"},
            "rankings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "photo_id": {"type": "string"},
                        "rank": {"type": "integer", "minimum": 1},
                        "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "technical_quality_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "storytelling_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "distinctiveness_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "theme_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "rationale": {"type": "string"},
                        "is_good_enough": {"type": "boolean"},
                    },
                    "required": [
                        "photo_id",
                        "rank",
                        "overall_score",
                        "technical_quality_score",
                        "storytelling_score",
                        "distinctiveness_score",
                        "theme_tags",
                        "rationale",
                        "is_good_enough",
                    ],
                },
            },
        },
        "required": ["day_name", "rankings"],
    }


def build_final_curation_schema() -> dict:
    """Return the strict JSON schema for one finalist-correlation response."""

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rankings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "photo_id": {"type": "string"},
                        "rank": {"type": "integer", "minimum": 1},
                        "keep_for_album": {"type": "boolean"},
                        "duplicate_of_photo_id": {"type": ["string", "null"]},
                        "materially_distinct_exception": {"type": "boolean"},
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "photo_id",
                        "rank",
                        "keep_for_album",
                        "duplicate_of_photo_id",
                        "materially_distinct_exception",
                        "rationale",
                    ],
                },
            }
        },
        "required": ["rankings"],
    }


def build_day_ranking_prompt(
    day_name: str,
    candidates: list[DayCandidatePhoto],
    selection_settings: SelectionSettings,
) -> tuple[str, str]:
    """Build the main text prompt and prompt-name metadata for one ranking run."""

    lines = [
        DEFAULT_RANKING_PROMPT,
        f"Day name: {day_name}",
        f"Number of photos to rank: {len(candidates)}",
        "Return a complete ordered ranking for all photos.",
        "Do not omit any photo, even weak ones. Weak photos should still appear at the end with is_good_enough=false.",
    ]
    prompt_name = DEFAULT_PROMPT_NAME

    if selection_settings.preference_prompt:
        lines.extend(
            [
                "",
                "Optional user preferences:",
                selection_settings.preference_prompt,
                "Treat the preferences as ranking guidance, not as a command to fill quotas.",
            ]
        )
        prompt_name = "default_plus_user_preferences"

    return "\n".join(lines), prompt_name


def build_final_curation_prompt(
    finalists: list[FinalistCandidate],
    selection_settings: SelectionSettings,
) -> tuple[str, str]:
    """Build the main text prompt and prompt-name metadata for shortlist curation."""

    lines = [
        FINALIST_CURATION_PROMPT,
        f"Number of shortlisted finalists: {len(finalists)}",
        "Return a complete ordered ranking for all shortlisted photos.",
        "Set keep_for_album=false for finalists that should be dropped from the album.",
        "Set duplicate_of_photo_id only when the weaker finalist repeats a stronger kept photo.",
    ]
    prompt_name = SECOND_PASS_PROMPT_NAME

    if selection_settings.preference_prompt:
        lines.extend(
            [
                "",
                "Optional user preferences:",
                selection_settings.preference_prompt,
                "Treat the preferences as ranking guidance, not as a command to keep more photos.",
            ]
        )
        prompt_name = "finalist_curation_plus_user_preferences"

    return "\n".join(lines), prompt_name


def build_day_ranking_input(
    day_name: str,
    candidates: list[DayCandidatePhoto],
    selection_settings: SelectionSettings,
    image_inputs: list[dict],
) -> tuple[list[dict], str]:
    """Build a Responses API multimodal input payload for one day."""

    prompt_text, prompt_name = build_day_ranking_prompt(day_name, candidates, selection_settings)
    content: list[dict] = [{"type": "input_text", "text": prompt_text}]
    for candidate, image_input in zip(candidates, image_inputs, strict=True):
        content.append({"type": "input_text", "text": f"Photo ID: {candidate.photo_id}"})
        content.append(image_input)

    return [{"role": "user", "content": content}], prompt_name


def build_final_curation_input(
    finalists: list[FinalistCandidate],
    selection_settings: SelectionSettings,
    image_inputs: list[dict],
) -> tuple[list[dict], str]:
    """Build a Responses API multimodal input payload for the finalist curation pass."""

    prompt_text, prompt_name = build_final_curation_prompt(finalists, selection_settings)
    content: list[dict] = [{"type": "input_text", "text": prompt_text}]
    for finalist, image_input in zip(finalists, image_inputs, strict=True):
        content.append({"type": "input_text", "text": f"Photo ID: {finalist.photo_id}"})
        content.append(image_input)

    return [{"role": "user", "content": content}], prompt_name


class OpenAIDayPhotoRanker:
    """OpenAI-backed ranker that handles both day ranking and shortlist curation."""

    def __init__(self, api_key: str, model_name: str) -> None:
        if OpenAI is None:
            raise RuntimeError(
                "The openai package is not installed. Add it to the environment before running Epic 3."
            )
        self._client = OpenAI(api_key=api_key)
        self._model_name = model_name

    def rank_day(
        self,
        day_name: str,
        candidates: list[DayCandidatePhoto],
        selection_settings: SelectionSettings,
    ) -> DayRankingBatch:
        if not candidates:
            return DayRankingBatch(
                day_name=day_name,
                rankings=(),
                prompt_name=DEFAULT_PROMPT_NAME,
                model_name=self._model_name,
                response_id=None,
            )

        prompt_name = build_day_ranking_prompt(day_name, candidates, selection_settings)[1]
        if _should_use_chat_completions_first(candidates, selection_settings):
            try:
                response, prompt_name = self._rank_day_via_chat_completions(
                    day_name,
                    candidates,
                    selection_settings,
                )
            except APIConnectionError as exc:
                raise RuntimeError(
                    "OpenAI connection failed while ranking day photos via the small-batch "
                    "Chat Completions path. Check network/proxy stability before retrying."
                ) from exc
        else:
            try:
                response, prompt_name = self._rank_day_via_responses(
                    day_name,
                    candidates,
                    selection_settings,
                )
            except APIConnectionError:
                try:
                    response, prompt_name = self._rank_day_via_chat_completions(
                        day_name,
                        candidates,
                        selection_settings,
                    )
                except APIConnectionError as fallback_exc:
                    raise RuntimeError(
                        "OpenAI connection failed while ranking day photos. "
                        "The primary Responses API path now uses uploaded JPEGs, and the "
                        "Chat Completions fallback also failed. Check network/proxy stability or "
                        "temporarily lower MAX_RANKING_CANDIDATES_PER_DAY in local_settings.py."
                    ) from fallback_exc

        parsed_payload = _extract_response_payload(response)
        ranking_items = parsed_payload["rankings"]
        total_count = len(candidates)
        rankings = [
            DayRankingRecord(
                photo_id=item["photo_id"],
                rank=int(item["rank"]),
                overall_score=float(item["overall_score"]),
                technical_quality_score=float(item["technical_quality_score"]),
                storytelling_score=float(item["storytelling_score"]),
                distinctiveness_score=float(item["distinctiveness_score"]),
                theme_tags=tuple(item["theme_tags"]),
                rationale=item["rationale"].strip(),
                is_good_enough=bool(item["is_good_enough"]),
                normalized_score=compute_normalized_score(
                    rank=int(item["rank"]),
                    total_count=total_count,
                    overall_score=float(item["overall_score"]),
                ),
            )
            for item in ranking_items
        ]
        validated_rankings = validate_day_rankings(day_name, candidates, rankings)

        return DayRankingBatch(
            day_name=day_name,
            rankings=tuple(validated_rankings),
            prompt_name=prompt_name,
            model_name=self._model_name,
            response_id=response.get("id") if isinstance(response, dict) else getattr(response, "id", None),
        )

    def curate_finalists(
        self,
        finalists: list[FinalistCandidate],
        selection_settings: SelectionSettings,
    ) -> FinalCurationBatch:
        if not finalists:
            return FinalCurationBatch(
                rankings=(),
                prompt_name=SECOND_PASS_PROMPT_NAME,
                model_name=self._model_name,
                response_id=None,
            )

        prompt_name = build_final_curation_prompt(finalists, selection_settings)[1]
        try:
            response, prompt_name = self._curate_finalists_via_responses(
                finalists,
                selection_settings,
            )
        except APIConnectionError:
            try:
                response, prompt_name = self._curate_finalists_via_chat_completions(
                    finalists,
                    selection_settings,
                )
            except APIConnectionError as fallback_exc:
                raise RuntimeError(
                    "OpenAI connection failed while curating final shortlist photos. "
                    "Both the Responses API path and the Chat Completions fallback failed."
                ) from fallback_exc

        parsed_payload = _extract_response_payload(response)
        ranking_items = parsed_payload["rankings"]
        rankings = [
            FinalCurationRecord(
                photo_id=item["photo_id"],
                rank=int(item["rank"]),
                keep_for_album=bool(item["keep_for_album"]),
                duplicate_of_photo_id=item["duplicate_of_photo_id"],
                materially_distinct_exception=bool(item["materially_distinct_exception"]),
                rationale=item["rationale"].strip(),
            )
            for item in ranking_items
        ]
        validated_rankings = validate_final_curation_records(finalists, rankings)
        return FinalCurationBatch(
            rankings=tuple(validated_rankings),
            prompt_name=prompt_name,
            model_name=self._model_name,
            response_id=response.get("id") if isinstance(response, dict) else getattr(response, "id", None),
        )

    def _rank_day_via_responses(
        self,
        day_name: str,
        candidates: list[DayCandidatePhoto],
        selection_settings: SelectionSettings,
    ):
        image_inputs = [
            self._upload_candidate_image(candidate.source_path, selection_settings, "ranking")
            for candidate in candidates
        ]
        request_input, prompt_name = build_day_ranking_input(
            day_name,
            candidates,
            selection_settings,
            image_inputs=image_inputs,
        )
        response = self._client.responses.create(
            model=self._model_name,
            input=request_input,
            max_output_tokens=_compute_output_token_budget(len(candidates), 120),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "day_photo_ranking",
                    "strict": True,
                    "schema": build_day_ranking_schema(),
                }
            },
        )
        return response, prompt_name

    def _rank_day_via_chat_completions(
        self,
        day_name: str,
        candidates: list[DayCandidatePhoto],
        selection_settings: SelectionSettings,
    ):
        messages, prompt_name = build_day_ranking_chat_messages(
            day_name=day_name,
            candidates=candidates,
            selection_settings=selection_settings,
        )
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            max_completion_tokens=_compute_output_token_budget(len(candidates), 120),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "day_photo_ranking",
                    "strict": True,
                    "schema": build_day_ranking_schema(),
                },
            },
        )
        return response, prompt_name

    def _curate_finalists_via_responses(
        self,
        finalists: list[FinalistCandidate],
        selection_settings: SelectionSettings,
    ):
        image_inputs = [
            self._upload_candidate_image(finalist.source_path, selection_settings, "curation")
            for finalist in finalists
        ]
        request_input, prompt_name = build_final_curation_input(
            finalists,
            selection_settings,
            image_inputs=image_inputs,
        )
        response = self._client.responses.create(
            model=self._model_name,
            input=request_input,
            max_output_tokens=_compute_output_token_budget(len(finalists), 80),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "finalist_curation",
                    "strict": True,
                    "schema": build_final_curation_schema(),
                }
            },
        )
        return response, prompt_name

    def _curate_finalists_via_chat_completions(
        self,
        finalists: list[FinalistCandidate],
        selection_settings: SelectionSettings,
    ):
        messages, prompt_name = build_final_curation_chat_messages(
            finalists=finalists,
            selection_settings=selection_settings,
        )
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            max_completion_tokens=_compute_output_token_budget(len(finalists), 80),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "finalist_curation",
                    "strict": True,
                    "schema": build_final_curation_schema(),
                },
            },
        )
        return response, prompt_name

    def _upload_candidate_image(
        self,
        source_path: Path,
        selection_settings: SelectionSettings,
        suffix: str,
    ) -> dict:
        buffer = _build_resized_jpeg_bytes(
            source_path,
            max_dimension=selection_settings.openai_upload_max_dimension,
            jpeg_quality=selection_settings.openai_upload_jpeg_quality,
        )
        file_name = f"{source_path.stem}_{suffix}.jpg"
        upload = self._client.files.create(file=(file_name, buffer, "image/jpeg"), purpose="vision")
        return {
            "type": "input_image",
            "file_id": upload.id,
        }


def _build_resized_jpeg_bytes(path: Path, max_dimension: int, jpeg_quality: int) -> io.BytesIO:
    with Image.open(path) as image:
        rgb_image = image.convert("RGB")
        rgb_image.thumbnail((max_dimension, max_dimension))
        output = io.BytesIO()
        rgb_image.save(output, format="JPEG", quality=jpeg_quality, optimize=True)
        output.seek(0)
        return output


def build_day_ranking_chat_messages(
    day_name: str,
    candidates: list[DayCandidatePhoto],
    selection_settings: SelectionSettings,
) -> tuple[list[dict], str]:
    """Build a Chat Completions multimodal message payload for fallback use."""

    prompt_text, prompt_name = build_day_ranking_prompt(day_name, candidates, selection_settings)
    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for candidate in candidates:
        jpeg_bytes = _build_resized_jpeg_bytes(
            candidate.source_path,
            max_dimension=min(selection_settings.openai_upload_max_dimension, 512),
            jpeg_quality=min(selection_settings.openai_upload_jpeg_quality, 70),
        ).getvalue()
        content.append({"type": "text", "text": f"Photo ID: {candidate.photo_id}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": _build_base64_data_url(jpeg_bytes),
                    "detail": "low",
                },
            }
        )
    return [{"role": "user", "content": content}], prompt_name


def build_final_curation_chat_messages(
    finalists: list[FinalistCandidate],
    selection_settings: SelectionSettings,
) -> tuple[list[dict], str]:
    """Build a Chat Completions multimodal message payload for finalist curation."""

    prompt_text, prompt_name = build_final_curation_prompt(finalists, selection_settings)
    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for finalist in finalists:
        jpeg_bytes = _build_resized_jpeg_bytes(
            finalist.source_path,
            max_dimension=min(selection_settings.openai_upload_max_dimension, 512),
            jpeg_quality=min(selection_settings.openai_upload_jpeg_quality, 70),
        ).getvalue()
        content.append({"type": "text", "text": f"Photo ID: {finalist.photo_id}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": _build_base64_data_url(jpeg_bytes),
                    "detail": "low",
                },
            }
        )
    return [{"role": "user", "content": content}], prompt_name


def _build_base64_data_url(jpeg_bytes: bytes) -> str:
    encoded = base64.b64encode(jpeg_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _extract_response_payload(response) -> dict:
    if hasattr(response, "output_text"):
        return json.loads(response.output_text)

    content = response.choices[0].message.content
    if content is None:
        raise ValueError("Chat Completions response did not include message content.")
    return json.loads(content)


def _should_use_chat_completions_first(
    candidates: list[DayCandidatePhoto],
    selection_settings: SelectionSettings,
) -> bool:
    limit = selection_settings.max_ranking_candidates_per_day
    return limit is not None and len(candidates) <= limit


def _compute_output_token_budget(item_count: int, tokens_per_item: int) -> int:
    """Return a generous but bounded token budget for structured output."""

    return min(16000, max(4000, item_count * tokens_per_item))
