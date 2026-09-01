"""R10 episode assembly/output contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


EpisodeOutputStatus = Literal[
    "READY",
    "WAITING_POSTPRODUCTION",
    "PROCESSING",
    "SUCCEEDED",
    "FAILED",
    "STALE",
]


class EpisodeSubtitleEventV1(_StrictModel):
    target_dialogue_id: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=1)
    text: str = Field(min_length=1)
    target_character_id: str | None = None
    target_character_name: str | None = None

    @model_validator(mode="after")
    def _range_valid(self) -> "EpisodeSubtitleEventV1":
        if self.end_us <= self.start_us:
            raise ValueError("subtitle event range invalid")
        return self


class EpisodeOutputSegmentV1(_StrictModel):
    generation_segment_id: str = Field(min_length=1)
    postproduction_status: str = Field(min_length=1)
    postproduction_fingerprint: str = Field(min_length=64, max_length=64)
    target_start_us: int = Field(ge=0)
    target_end_us: int = Field(ge=1)
    target_duration_us: int = Field(ge=1)
    output_path: str | None = None


class EpisodeOutputV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    episode_title: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=64, max_length=64)
    status: EpisodeOutputStatus
    reason: str = Field(min_length=1)
    segment_count: int = Field(ge=0)
    target_duration_us: int = Field(ge=0)
    segments: list[EpisodeOutputSegmentV1] = Field(default_factory=list)
    subtitles: list[EpisodeSubtitleEventV1] = Field(default_factory=list)
    subtitle_path: str | None = None
    output_path: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _counts(self) -> "EpisodeOutputV1":
        if self.segment_count != len(self.segments):
            raise ValueError("episode output segment_count mismatch")
        if self.status == "SUCCEEDED" and not self.output_path:
            raise ValueError("successful episode output needs output_path")
        return self


class EpisodeOutputPlanV1(_StrictModel):
    schema_version: Literal["episode-output-plan-v1"] = "episode-output-plan-v1"
    project_id: str = Field(min_length=1)
    status: EpisodeOutputStatus
    episode_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    waiting_count: int = Field(ge=0)
    episodes: list[EpisodeOutputV1] = Field(default_factory=list)


__all__ = [
    "EpisodeOutputPlanV1",
    "EpisodeOutputSegmentV1",
    "EpisodeOutputStatus",
    "EpisodeOutputV1",
    "EpisodeSubtitleEventV1",
]
