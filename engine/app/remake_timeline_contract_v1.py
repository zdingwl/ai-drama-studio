"""R6 Dialogue Timing Engine / RemakeTimeline contract."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


TimingStrategy = Literal[
    "KEEP",
    "TRIM",
    "CARRY_OVER_REACTION",
    "EXTEND",
    "REWRITE_SHORTER",
    "HUMAN_REVIEW",
]


class RemakeDialoguePlanV1(_StrictModel):
    target_dialogue_id: str = Field(min_length=1)
    source_dialogue_key: str = Field(min_length=1)
    source_character_id: str | None = None
    target_character_id: str | None = None
    source_start_us: int = Field(ge=0)
    source_end_us: int = Field(ge=0)
    source_window_us: int = Field(ge=0)
    speech_duration_us: int = Field(ge=1)
    planned_start_offset_us: int = Field(ge=0)
    planned_end_offset_us: int = Field(ge=1)
    planned_start_us: int = Field(ge=0)
    planned_end_us: int = Field(ge=1)
    strategy: TimingStrategy
    carry_over_shot_key: str | None = None
    overrun_us: int = Field(ge=0)
    reason: str = Field(min_length=1)


class RemakeShotPlanV1(_StrictModel):
    shot_plan_id: str = Field(min_length=1)
    scene_key: str = Field(min_length=1)
    shot_key: str = Field(min_length=1)
    source_shot_id: str | None = None
    ordinal: int = Field(ge=1)
    reference_url: str | None = None
    source_start_us: int = Field(ge=0)
    source_end_us: int = Field(ge=0)
    source_duration_us: int = Field(ge=1)
    planned_start_us: int = Field(ge=0)
    planned_end_us: int = Field(ge=1)
    planned_duration_us: int = Field(ge=1)
    duration_delta_us: int
    strategy: TimingStrategy
    status: Literal["READY", "REVIEW", "WAITING_AUDIO"]
    decision_source: Literal["AUTO", "MANUAL"]
    reason: str = Field(min_length=1)
    dialogue_plans: list[RemakeDialoguePlanV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _timing_is_consistent(self) -> "RemakeShotPlanV1":
        if self.source_end_us < self.source_start_us:
            raise ValueError("source Shot range invalid")
        if self.planned_end_us - self.planned_start_us != self.planned_duration_us:
            raise ValueError("planned Shot duration mismatch")
        if self.duration_delta_us != self.planned_duration_us - self.source_duration_us:
            raise ValueError("duration_delta_us mismatch")
        return self


class RemakeEpisodeTimelineV1(_StrictModel):
    schema_version: Literal["remake-timeline-v1"] = "remake-timeline-v1"
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_dialogue_fingerprint: str = Field(min_length=64, max_length=64)
    status: Literal["READY", "REVIEW", "WAITING_AUDIO"]
    source_duration_us: int = Field(ge=0)
    planned_duration_us: int = Field(ge=0)
    duration_delta_us: int
    shot_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_audio_count: int = Field(ge=0)
    shot_plans: list[RemakeShotPlanV1] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _counts_match(self) -> "RemakeEpisodeTimelineV1":
        if self.shot_count != len(self.shot_plans):
            raise ValueError("shot_count mismatch")
        reviews = sum(item.status == "REVIEW" for item in self.shot_plans)
        waiting = sum(item.status == "WAITING_AUDIO" for item in self.shot_plans)
        if self.review_count != reviews:
            raise ValueError("review_count mismatch")
        if self.waiting_audio_count != waiting:
            raise ValueError("waiting_audio_count mismatch")
        if self.duration_delta_us != self.planned_duration_us - self.source_duration_us:
            raise ValueError("episode duration_delta_us mismatch")
        if self.status == "READY" and (reviews or waiting):
            raise ValueError("READY timeline cannot contain review/waiting Shot")
        if self.status == "REVIEW" and not reviews:
            raise ValueError("REVIEW timeline needs review Shot")
        if self.status == "WAITING_AUDIO" and reviews:
            raise ValueError("WAITING_AUDIO timeline cannot hide human review")
        return self


class RemakeProjectTimelineV1(_StrictModel):
    schema_version: Literal["remake-project-timeline-v1"] = "remake-project-timeline-v1"
    project_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_dialogue_fingerprint: str = Field(min_length=64, max_length=64)
    status: Literal["READY", "REVIEW", "WAITING_AUDIO"]
    episode_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_audio_count: int = Field(ge=0)
    episodes: list[RemakeEpisodeTimelineV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_match(self) -> "RemakeProjectTimelineV1":
        if self.episode_count != len(self.episodes):
            raise ValueError("episode_count mismatch")
        if self.review_count != sum(item.review_count for item in self.episodes):
            raise ValueError("project review_count mismatch")
        if self.waiting_audio_count != sum(item.waiting_audio_count for item in self.episodes):
            raise ValueError("project waiting_audio_count mismatch")
        if any(item.source_fingerprint != self.source_fingerprint for item in self.episodes):
            raise ValueError("episode source fingerprint mismatch")
        if any(item.target_dialogue_fingerprint != self.target_dialogue_fingerprint for item in self.episodes):
            raise ValueError("episode dialogue fingerprint mismatch")
        return self


__all__ = [
    "RemakeDialoguePlanV1",
    "RemakeEpisodeTimelineV1",
    "RemakeProjectTimelineV1",
    "RemakeShotPlanV1",
    "TimingStrategy",
]
