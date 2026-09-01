"""R10 postproduction contracts.

R10 consumes only current GenerationSelection + GenerationSegment dialogue/timing truth.
It never mutates H3 attempts, QC results, source facts, target dialogue, or RemakeTimeline.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


PostProductionStatus = Literal[
    "READY",
    "WAITING_SELECTION",
    "WAITING_AUDIO",
    "WAITING_MODEL",
    "REVIEW",
    "PROCESSING",
    "SUCCEEDED",
    "FAILED",
    "STALE",
]
LipSyncMode = Literal[
    "SKIP_NO_VISIBLE_DIALOGUE",
    "LATENTSYNC_FULL_SEGMENT",
    "LATENTSYNC_TARGET_FACE_ROI",
    "REVIEW_MULTI_FACE",
]


class PostProductionDialogueV1(_StrictModel):
    target_dialogue_id: str = Field(min_length=1)
    target_character_id: str | None = None
    target_character_name: str | None = None
    final_text: str | None = None
    audio_path: str = Field(min_length=1)
    audio_trim_start_us: int = Field(ge=0)
    start_offset_us: int = Field(ge=0)
    end_offset_us: int = Field(ge=1)
    speaker_visible: bool

    @model_validator(mode="after")
    def _range(self) -> "PostProductionDialogueV1":
        if self.end_offset_us <= self.start_offset_us:
            raise ValueError("postproduction dialogue range invalid")
        return self


class PostProductionSegmentV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    generation_segment_id: str = Field(min_length=1)
    segment_input_fingerprint: str = Field(min_length=64, max_length=64)
    selection_id: str | None = None
    selected_attempt_id: str | None = None
    postproduction_fingerprint: str = Field(min_length=64, max_length=64)
    target_start_us: int = Field(ge=0)
    target_end_us: int = Field(ge=1)
    target_duration_us: int = Field(ge=1)
    status: PostProductionStatus
    reason: str = Field(min_length=1)
    lip_sync_mode: LipSyncMode
    visible_character_count: int = Field(ge=0)
    visible_speaker_ids: list[str] = Field(default_factory=list)
    locator_input_fingerprint: str | None = None
    lip_sync_windows: list[dict[str, Any]] = Field(default_factory=list)
    dialogues: list[PostProductionDialogueV1] = Field(default_factory=list)
    audio_path: str | None = None
    output_path: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _consistent(self) -> "PostProductionSegmentV1":
        if self.target_end_us - self.target_start_us != self.target_duration_us:
            raise ValueError("postproduction target duration mismatch")
        if self.lip_sync_mode == "LATENTSYNC_FULL_SEGMENT" and self.visible_character_count != 1:
            raise ValueError("LatentSync full-segment auto mode requires exactly one visible character")
        if self.lip_sync_mode == "LATENTSYNC_TARGET_FACE_ROI" and self.visible_character_count < 2:
            raise ValueError("target-face ROI mode is reserved for multi-person visible segments")
        if self.status == "SUCCEEDED" and not self.output_path:
            raise ValueError("successful postproduction segment needs output_path")
        return self


class PostProductionEpisodeV1(_StrictModel):
    episode_id: str = Field(min_length=1)
    status: PostProductionStatus
    segment_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_count: int = Field(ge=0)
    segments: list[PostProductionSegmentV1] = Field(default_factory=list)


class PostProductionPlanV1(_StrictModel):
    schema_version: Literal["postproduction-plan-v1"] = "postproduction-plan-v1"
    project_id: str = Field(min_length=1)
    status: PostProductionStatus
    episode_count: int = Field(ge=0)
    segment_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_count: int = Field(ge=0)
    episodes: list[PostProductionEpisodeV1] = Field(default_factory=list)


class LipSyncRuntimeStatusV1(_StrictModel):
    runtime_profile: Literal["LATENTSYNC_LOCAL_V1_6"] = "LATENTSYNC_LOCAL_V1_6"
    ready: bool
    reachable: bool
    base_url: str
    worker: dict = Field(default_factory=dict)
    error: str | None = None


__all__ = [
    "LipSyncMode",
    "LipSyncRuntimeStatusV1",
    "PostProductionDialogueV1",
    "PostProductionEpisodeV1",
    "PostProductionPlanV1",
    "PostProductionSegmentV1",
    "PostProductionStatus",
]
