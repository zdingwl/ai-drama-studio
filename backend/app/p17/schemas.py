from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator
from app.p15.schemas import GenerationAudioMode


P17_SCHEMA_VERSION = "1.0"
P17_SKILL_ID = "post-production"
P17_CONTRACT = "replica-post-final-output-v1"
P17_LIP_SYNC_CONTRACT = "local-http-lip-sync-v1"


class P17ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class PostReviewStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class FinalEpisodeOutput(BaseModel):
    episode_id: str
    episode_order: int = Field(ge=1)
    video_url: str
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = "video/mp4"
    duration_us: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    codec_name: str
    subtitle_url: str
    subtitle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lip_synced_segment_count: int = Field(ge=0)
    segment_count: int = Field(ge=1)


class ReplicaFinalOutputContent(BaseModel):
    schema_version: str = P17_SCHEMA_VERSION
    title: str = "复刻最终成片"
    generation_selection_artifact_id: str
    audio_generation_mode: GenerationAudioMode = GenerationAudioMode.NATIVE_AUDIO_VIDEO
    target_audio_artifact_id: str | None = None
    target_script_artifact_id: str
    timing_plan_artifact_id: str | None = None
    episodes: list[FinalEpisodeOutput] = Field(min_length=1)


class P17CandidateProvenance(BaseModel):
    generation_selection_artifact_id: str
    generation_selection_revision: int
    generation_selection_fingerprint: str
    audio_generation_mode: GenerationAudioMode = GenerationAudioMode.NATIVE_AUDIO_VIDEO
    target_audio_artifact_id: str | None = None
    target_audio_revision: int | None = None
    target_audio_fingerprint: str | None = None
    target_script_artifact_id: str
    target_script_revision: int
    target_script_fingerprint: str
    timing_plan_artifact_id: str | None = None
    timing_plan_revision: int | None = None
    timing_plan_fingerprint: str | None = None
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = P17_SKILL_ID
    professional_skill_version: str
    schema_version: str = P17_SCHEMA_VERSION
    contract: str = P17_CONTRACT
    lip_sync_contract: str = P17_LIP_SYNC_CONTRACT
    lip_sync_provider_job_ids: list[str] = Field(default_factory=list)
    generated_by_task_id: str


class P17ArtifactProvenance(P17CandidateProvenance):
    candidate_id: str
    reviewed_by: str = "USER_EXPLICIT_ACTION"
    reviewed_at: datetime
    review_reason: str
    supersedes_artifact_id: str | None = None


class PostCandidateRead(BaseModel):
    id: str
    project_id: str
    generation_sequence: int
    input_fingerprint: str
    review_status: PostReviewStatus
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    content: ReplicaFinalOutputContent
    provenance: P17CandidateProvenance


class ReplicaFinalOutputRead(BaseModel):
    project_id: str
    status: P17ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaFinalOutputContent | None = None
    provenance: P17ArtifactProvenance | None = None


class P17ReviewCommand(BaseModel):
    expected_generation_selection_artifact_id: str
    expected_target_audio_artifact_id: str | None = None
    expected_target_script_artifact_id: str
    expected_timing_plan_artifact_id: str | None = None
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("review reason cannot be blank")
        return normalized
