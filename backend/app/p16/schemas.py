from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


P16_SCHEMA_VERSION = "1.0"
P16_SKILL_ID = "video-generation-qc"
P16_CONTRACT = "h3-generation-runtime-qc-selection-v2"


class P16ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class H3RuntimeReadinessState(StrEnum):
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    WARMING_UP = "WARMING_UP"
    INCOMPATIBLE = "INCOMPATIBLE"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class H3RuntimeReadinessRead(BaseModel):
    runtime_mode: str
    state: H3RuntimeReadinessState
    ready: bool
    provider: str
    model: str
    base_url: str
    message: str


class TechnicalQcStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class SelectionReviewStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class GenerationAttemptRead(BaseModel):
    id: str
    project_id: str
    generation_segment_id: str
    attempt_number: int = Field(ge=1)
    provider_job_id: str
    provider: str
    model: str
    remote_job_id: str | None = None
    media_url: str
    media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str
    actual_duration_us: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    codec_name: str
    technical_qc_status: TechnicalQcStatus
    technical_qc_issues: list[str] = Field(default_factory=list)
    created_at: datetime


class SelectedGenerationClip(BaseModel):
    generation_segment_id: str
    episode_id: str
    episode_order: int = Field(ge=1)
    segment_number: int = Field(ge=1)
    planned_start_us: int = Field(ge=0)
    planned_end_us: int = Field(gt=0)
    planned_duration_us: int = Field(gt=0)
    requires_lip_sync: bool
    selected_attempt_id: str
    provider_job_id: str
    media_url: str
    media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str
    actual_duration_us: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    codec_name: str


class ReplicaGeneratedVideoContent(BaseModel):
    schema_version: str = P16_SCHEMA_VERSION
    title: str = "正式生成视频片段"
    target_storyboard_artifact_id: str
    generation_segments_artifact_id: str
    target_assets_artifact_id: str
    clips: list[SelectedGenerationClip] = Field(min_length=1)


class GenerationSelectionItem(BaseModel):
    generation_segment_id: str
    selected_attempt_id: str


class ReplicaGenerationSelectionContent(BaseModel):
    schema_version: str = P16_SCHEMA_VERSION
    title: str = "视频生成正式选片"
    target_storyboard_artifact_id: str
    generation_segments_artifact_id: str
    target_assets_artifact_id: str
    generated_video_artifact_id: str | None = None
    selections: list[GenerationSelectionItem] = Field(min_length=1)


class P16SelectionCandidateContent(BaseModel):
    target_storyboard_artifact_id: str
    generation_segments_artifact_id: str
    target_assets_artifact_id: str
    clips: list[SelectedGenerationClip] = Field(min_length=1)


class P16CandidateProvenance(BaseModel):
    target_storyboard_artifact_id: str
    target_storyboard_revision: int
    target_storyboard_fingerprint: str
    generation_segments_artifact_id: str
    generation_segments_revision: int
    generation_segments_fingerprint: str
    target_assets_artifact_id: str
    target_assets_revision: int
    target_assets_fingerprint: str
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = P16_SKILL_ID
    professional_skill_version: str
    schema_version: str = P16_SCHEMA_VERSION
    contract: str = P16_CONTRACT
    provider: str
    model: str
    provider_job_ids: list[str] = Field(default_factory=list)
    generated_by_task_id: str


class P16ArtifactProvenance(P16CandidateProvenance):
    selection_candidate_id: str
    reviewed_by: str = "USER_EXPLICIT_ACTION"
    reviewed_at: datetime
    review_reason: str
    supersedes_artifact_id: str | None = None


class P16SelectionCandidateRead(BaseModel):
    id: str
    project_id: str
    generation_sequence: int
    input_fingerprint: str
    review_status: SelectionReviewStatus
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    content: P16SelectionCandidateContent
    provenance: P16CandidateProvenance


class ReplicaGeneratedVideoRead(BaseModel):
    project_id: str
    status: P16ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaGeneratedVideoContent | None = None
    provenance: P16ArtifactProvenance | None = None


class ReplicaGenerationSelectionRead(BaseModel):
    project_id: str
    status: P16ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaGenerationSelectionContent | None = None
    provenance: P16ArtifactProvenance | None = None


class P16ReviewCommand(BaseModel):
    expected_target_storyboard_artifact_id: str
    expected_generation_segments_artifact_id: str
    expected_target_assets_artifact_id: str
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("review reason cannot be blank")
        return value
