"""R7 GenerationSegment contract.

GenerationSegment is the stable boundary between remake planning and H3 execution.
It compiles source direction, localized target assets, target dialogue and RemakeTimeline
into executable H3-sized units without mutating any upstream truth.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


GenerationSegmentStatus = Literal["READY", "REVIEW", "WAITING_AUDIO"]
GenerationMode = Literal["REF2VA", "FL2VA"]


class GenerationCharacterContextV1(_StrictModel):
    source_character_id: str = Field(min_length=1)
    target_character_id: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    appearance_profile: str = Field(min_length=1)
    generation_prompt: str = Field(min_length=1)
    reference_assets: list[str] = Field(default_factory=list)


class GenerationSceneContextV1(_StrictModel):
    mapping_id: str = Field(min_length=1)
    source_scene_id: str | None = None
    source_scene_name: str | None = None
    decision: Literal["KEEP", "LOCALIZE"]
    target_label: str | None = None
    target_description: str | None = None


class GenerationDialogueSliceV1(_StrictModel):
    target_dialogue_id: str = Field(min_length=1)
    source_dialogue_key: str = Field(min_length=1)
    origin_shot_key: str = Field(min_length=1)
    target_character_id: str | None = None
    target_character_name: str | None = None
    final_text: str | None = None
    audio_status: str = Field(min_length=1)
    audio_path: str | None = None
    global_start_us: int = Field(ge=0)
    global_end_us: int = Field(ge=1)
    segment_start_offset_us: int = Field(ge=0)
    segment_end_offset_us: int = Field(ge=1)
    speaker_visible: bool
    carried_from_previous_shot: bool

    @model_validator(mode="after")
    def _range_valid(self) -> "GenerationDialogueSliceV1":
        if self.global_end_us <= self.global_start_us:
            raise ValueError("dialogue global range invalid")
        if self.segment_end_offset_us <= self.segment_start_offset_us:
            raise ValueError("dialogue segment range invalid")
        return self


class GenerationSegmentV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    remake_timeline_id: str = Field(min_length=1)
    shot_plan_id: str = Field(min_length=1)
    scene_key: str = Field(min_length=1)
    shot_key: str = Field(min_length=1)
    source_shot_id: str | None = None
    shot_ordinal: int = Field(ge=1)
    shot_segment_index: int = Field(ge=1)
    shot_segment_count: int = Field(ge=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_dialogue_fingerprint: str = Field(min_length=64, max_length=64)
    target_localization_fingerprint: str = Field(min_length=64, max_length=64)
    remake_timeline_fingerprint: str = Field(min_length=64, max_length=64)
    upstream_fingerprint: str = Field(min_length=64, max_length=64)
    input_fingerprint: str = Field(min_length=64, max_length=64)
    target_start_us: int = Field(ge=0)
    target_end_us: int = Field(ge=1)
    target_duration_us: int = Field(ge=1)
    h3_duration_us: int = Field(ge=4_000_000, le=15_000_000)
    post_trim_duration_us: int | None = Field(default=None, ge=1)
    timing_strategy: str = Field(min_length=1)
    generation_mode: GenerationMode
    reference_url: str | None = None
    reference_clip_start_offset_us: int | None = Field(default=None, ge=0)
    reference_clip_duration_us: int | None = Field(default=None, ge=1)
    continuity_from_segment_id: str | None = None
    status: GenerationSegmentStatus
    reason: str = Field(min_length=1)
    visual_description: str | None = None
    performance: list[dict[str, Any]] = Field(default_factory=list)
    cinematography: dict[str, Any] = Field(default_factory=dict)
    observed_props: list[dict[str, Any]] = Field(default_factory=list)
    final_props: list[dict[str, Any]] = Field(default_factory=list)
    target_scene: GenerationSceneContextV1 | None = None
    target_characters: list[GenerationCharacterContextV1] = Field(default_factory=list)
    dialogues: list[GenerationDialogueSliceV1] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _segment_consistent(self) -> "GenerationSegmentV1":
        if self.target_end_us - self.target_start_us != self.target_duration_us:
            raise ValueError("GenerationSegment target duration mismatch")
        if self.shot_segment_index > self.shot_segment_count:
            raise ValueError("GenerationSegment index exceeds count")
        if self.h3_duration_us < self.target_duration_us:
            raise ValueError("H3 render duration cannot be shorter than target segment")
        if self.h3_duration_us != self.target_duration_us and self.post_trim_duration_us != self.target_duration_us:
            raise ValueError("quantized H3 duration must expose post trim target")
        if self.h3_duration_us == self.target_duration_us and self.post_trim_duration_us is not None:
            raise ValueError("exact H3 duration must not expose redundant post trim")
        if self.generation_mode == "REF2VA":
            if not self.reference_url:
                raise ValueError("REF2VA segment needs reference video")
            if self.reference_clip_duration_us is None or not (2_000_000 <= self.reference_clip_duration_us <= 15_000_000):
                raise ValueError("REF2VA reference video must be 2-15 seconds")
        return self


class GenerationEpisodePlanV1(_StrictModel):
    episode_id: str = Field(min_length=1)
    remake_timeline_id: str = Field(min_length=1)
    status: GenerationSegmentStatus
    segment_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_audio_count: int = Field(ge=0)
    segments: list[GenerationSegmentV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_match(self) -> "GenerationEpisodePlanV1":
        if self.segment_count != len(self.segments):
            raise ValueError("episode segment_count mismatch")
        if self.review_count != sum(item.status == "REVIEW" for item in self.segments):
            raise ValueError("episode review_count mismatch")
        if self.waiting_audio_count != sum(item.status == "WAITING_AUDIO" for item in self.segments):
            raise ValueError("episode waiting_audio_count mismatch")
        return self


class GenerationSegmentPlanV1(_StrictModel):
    schema_version: Literal["generation-segment-plan-v1"] = "generation-segment-plan-v1"
    project_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_dialogue_fingerprint: str = Field(min_length=64, max_length=64)
    target_localization_fingerprint: str = Field(min_length=64, max_length=64)
    remake_timeline_fingerprint: str = Field(min_length=64, max_length=64)
    upstream_fingerprint: str = Field(min_length=64, max_length=64)
    status: GenerationSegmentStatus
    episode_count: int = Field(ge=0)
    segment_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_audio_count: int = Field(ge=0)
    episodes: list[GenerationEpisodePlanV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_match(self) -> "GenerationSegmentPlanV1":
        if self.episode_count != len(self.episodes):
            raise ValueError("project episode_count mismatch")
        if self.segment_count != sum(item.segment_count for item in self.episodes):
            raise ValueError("project segment_count mismatch")
        if self.review_count != sum(item.review_count for item in self.episodes):
            raise ValueError("project review_count mismatch")
        if self.waiting_audio_count != sum(item.waiting_audio_count for item in self.episodes):
            raise ValueError("project waiting_audio_count mismatch")
        if self.status == "READY" and (self.review_count or self.waiting_audio_count):
            raise ValueError("READY generation plan cannot contain blockers")
        if self.status == "REVIEW" and not self.review_count:
            raise ValueError("REVIEW generation plan needs review segments")
        if self.status == "WAITING_AUDIO" and self.review_count:
            raise ValueError("WAITING_AUDIO plan cannot hide review segments")
        return self


__all__ = [
    "GenerationCharacterContextV1",
    "GenerationDialogueSliceV1",
    "GenerationEpisodePlanV1",
    "GenerationMode",
    "GenerationSceneContextV1",
    "GenerationSegmentPlanV1",
    "GenerationSegmentStatus",
    "GenerationSegmentV1",
]
