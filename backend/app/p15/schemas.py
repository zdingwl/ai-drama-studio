from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.shot_breakdown.schemas import CameraLanguage, DialogueDelivery
from app.target_assets.schemas import TargetAssetRef


P15_SCHEMA_VERSION = "1.0"
P15_SKILL_ID = "storyboard-directing"
P15_CONTRACT = "replica-storyboard-generation-segments-v1"
P15_COMPILE_MODE = "DETERMINISTIC_REPLICA_COMPILE"


class P15ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class P15CandidateReviewStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class StoryboardDialogueRef(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    delivery: DialogueDelivery
    target_character_id: str | None = None
    final_target_dialogue: str
    target_audio_clip_id: str
    media_url: str
    planned_speech_start_us: int = Field(ge=0)
    planned_speech_end_us: int = Field(gt=0)


class TargetStoryboardShot(BaseModel):
    storyboard_shot_id: str
    episode_id: str
    episode_order: int = Field(ge=1)
    source_shot_anchor_id: str
    shot_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    duration_us: int = Field(gt=0)
    camera_language: CameraLanguage
    source_visual_description: str
    target_visual_description: str
    target_scene_ids: list[str] = Field(default_factory=list)
    target_character_ids: list[str] = Field(default_factory=list)
    target_prop_ids: list[str] = Field(default_factory=list)
    target_asset_refs: list[TargetAssetRef] = Field(default_factory=list)
    dialogue_refs: list[StoryboardDialogueRef] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    sound_effects: list[str] = Field(default_factory=list)
    ambience: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timing(self) -> "TargetStoryboardShot":
        if self.end_us <= self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("storyboard shot timing must preserve Source Shot timing")
        return self


class ReplicaTargetStoryboardContent(BaseModel):
    schema_version: str = P15_SCHEMA_VERSION
    title: str = "复刻目标分镜"
    source_snapshot_artifact_id: str
    target_bible_artifact_id: str
    target_script_artifact_id: str
    target_assets_artifact_id: str
    target_audio_artifact_id: str
    timing_plan_artifact_id: str
    target_language: str
    target_region: str
    shots: list[TargetStoryboardShot] = Field(min_length=1)


class GenerationSegment(BaseModel):
    generation_segment_id: str
    episode_id: str
    episode_order: int = Field(ge=1)
    segment_number: int = Field(ge=1)
    storyboard_shot_ids: list[str] = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    duration_us: int = Field(gt=0)
    output_ratio: str = Field(pattern=r"^(21:9|16:9|4:3|1:1|3:4|9:16)$")
    continuation_index: int = Field(ge=1)
    continuation_count: int = Field(ge=1)
    generation_prompt: str = Field(min_length=1, max_length=12000)
    negative_prompt: str = Field(default="", max_length=6000)
    target_asset_refs: list[TargetAssetRef] = Field(default_factory=list)
    requires_lip_sync: bool = False

    @model_validator(mode="after")
    def validate_segment(self) -> "GenerationSegment":
        if self.end_us <= self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("generation segment timing is invalid")
        if self.continuation_index > self.continuation_count:
            raise ValueError("continuation_index cannot exceed continuation_count")
        return self


class ReplicaGenerationSegmentsContent(BaseModel):
    schema_version: str = P15_SCHEMA_VERSION
    title: str = "视频生成分段计划"
    target_storyboard_artifact_id: str | None = None
    target_assets_artifact_id: str
    max_segment_duration_us: int = Field(gt=0)
    segments: list[GenerationSegment] = Field(min_length=1)


class ReplicaStoryboardBundle(BaseModel):
    storyboard: ReplicaTargetStoryboardContent
    generation_segments: ReplicaGenerationSegmentsContent


class P15CandidateProvenance(BaseModel):
    source_snapshot_artifact_id: str
    source_snapshot_revision: int
    source_snapshot_fingerprint: str
    target_bible_artifact_id: str
    target_bible_revision: int
    target_bible_fingerprint: str
    target_script_artifact_id: str
    target_script_revision: int
    target_script_fingerprint: str
    target_assets_artifact_id: str
    target_assets_revision: int
    target_assets_fingerprint: str
    target_audio_artifact_id: str
    target_audio_revision: int
    target_audio_fingerprint: str
    timing_plan_artifact_id: str
    timing_plan_revision: int
    timing_plan_fingerprint: str
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = P15_SKILL_ID
    professional_skill_version: str
    schema_version: str = P15_SCHEMA_VERSION
    contract: str = P15_CONTRACT
    compile_mode: str = P15_COMPILE_MODE
    generated_by_task_id: str
    provider_jobs: list[dict] = Field(default_factory=list, max_length=0)


class P15ArtifactProvenance(P15CandidateProvenance):
    candidate_id: str
    reviewed_by: str = "USER_EXPLICIT_ACTION"
    reviewed_at: datetime
    review_reason: str
    supersedes_artifact_id: str | None = None


class P15CandidateRead(BaseModel):
    id: str
    project_id: str
    generation_sequence: int
    input_fingerprint: str
    review_status: P15CandidateReviewStatus
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    content: ReplicaStoryboardBundle
    provenance: P15CandidateProvenance


class ReplicaTargetStoryboardRead(BaseModel):
    project_id: str
    status: P15ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaTargetStoryboardContent | None = None
    provenance: P15ArtifactProvenance | None = None


class ReplicaGenerationSegmentsRead(BaseModel):
    project_id: str
    status: P15ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaGenerationSegmentsContent | None = None
    provenance: P15ArtifactProvenance | None = None


class P15ReviewCommand(BaseModel):
    expected_source_snapshot_artifact_id: str
    expected_target_bible_artifact_id: str
    expected_target_script_artifact_id: str
    expected_target_assets_artifact_id: str
    expected_target_audio_artifact_id: str
    expected_timing_plan_artifact_id: str
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("review reason cannot be blank")
        return value
