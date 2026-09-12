from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


P14_AUDIO_SCHEMA_VERSION = "1.0"
P14_AUDIO_SKILL_ID = "replica-target-audio"
P14_AUDIO_CONTRACT = "replica-target-audio-v1"
P14_AUDIO_PROVIDER_CONTRACT = "target-dialogue-tts-media-v1"
P14_TIMING_SCHEMA_VERSION = "1.0"
P14_TIMING_SKILL_ID = "replica-dialogue-timing"
P14_TIMING_CONTRACT = "actual-speech-duration-timing-v1"


class P14ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class CandidateReviewStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class VoiceBindingScope(StrEnum):
    CHARACTER = "CHARACTER"
    UTTERANCE = "UTTERANCE"


class TargetVoiceBinding(BaseModel):
    scope: VoiceBindingScope
    target_character_id: str | None = Field(default=None, max_length=160)
    utterance_id: str | None = Field(default=None, max_length=160)
    voice_id: str = Field(min_length=1, max_length=160)
    voice_label: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_scope_key(self) -> "TargetVoiceBinding":
        if self.scope == VoiceBindingScope.CHARACTER:
            if not self.target_character_id or self.utterance_id:
                raise ValueError("CHARACTER voice binding requires only target_character_id")
        elif not self.utterance_id or self.target_character_id:
            raise ValueError("UTTERANCE voice binding requires only utterance_id")
        return self


class TargetAudioGenerateCommand(BaseModel):
    bindings: list[TargetVoiceBinding] = Field(min_length=1, max_length=2000)


class TargetAudioClip(BaseModel):
    clip_id: str
    episode_id: str
    episode_order: int = Field(ge=1)
    utterance_id: str
    utterance_number: int = Field(ge=1)
    target_character_id: str | None = None
    final_target_dialogue: str
    final_target_dialogue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    voice_id: str
    voice_label: str | None = None
    provider: str
    model: str
    provider_job_id: str
    media_url: str
    media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str
    actual_speech_duration_us: int = Field(gt=0)
    sample_rate_hz: int | None = Field(default=None, gt=0)
    channel_count: int | None = Field(default=None, gt=0)


class ReplicaTargetAudioContent(BaseModel):
    schema_version: str = P14_AUDIO_SCHEMA_VERSION
    title: str = "目标配音"
    target_language: str
    target_region: str
    target_script_artifact_id: str
    target_bible_artifact_id: str
    clips: list[TargetAudioClip] = Field(default_factory=list, max_length=20000)


class TargetAudioCandidateProvenance(BaseModel):
    target_script_artifact_id: str
    target_script_revision: int
    target_script_fingerprint: str
    target_bible_artifact_id: str
    target_bible_revision: int
    target_bible_fingerprint: str
    target_language: str
    target_region: str
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = P14_AUDIO_SKILL_ID
    professional_skill_version: str
    provider: str
    model: str
    provider_job_ids: list[str] = Field(default_factory=list)
    provider_contract: str = P14_AUDIO_PROVIDER_CONTRACT
    generated_by_task_id: str


class TargetAudioProvenance(TargetAudioCandidateProvenance):
    candidate_id: str
    reviewed_at: str
    review_reason: str
    supersedes_artifact_id: str | None = None


class TargetAudioCandidateRead(BaseModel):
    id: str
    project_id: str
    target_script_artifact_id: str
    target_bible_artifact_id: str
    generated_by_task_id: str | None = None
    generation_sequence: int
    input_fingerprint: str
    review_status: CandidateReviewStatus
    review_reason: str | None = None
    reviewed_at: str | None = None
    created_at: str
    content: ReplicaTargetAudioContent
    provenance: TargetAudioCandidateProvenance


class TargetAudioReviewCommand(BaseModel):
    expected_target_script_artifact_id: str
    expected_target_bible_artifact_id: str
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)


class ReplicaTargetAudioRead(BaseModel):
    project_id: str
    status: P14ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaTargetAudioContent | None = None
    provenance: TargetAudioProvenance | None = None


class TimingFitStatus(StrEnum):
    FIT = "FIT"
    OVERFLOW = "OVERFLOW"


class TimingDialogueItem(BaseModel):
    episode_id: str
    episode_order: int = Field(ge=1)
    utterance_id: str
    utterance_number: int = Field(ge=1)
    target_character_id: str | None = None
    source_start_us: int = Field(ge=0)
    source_end_us: int = Field(gt=0)
    source_slot_duration_us: int = Field(gt=0)
    actual_speech_duration_us: int = Field(gt=0)
    planned_speech_start_us: int = Field(ge=0)
    planned_speech_end_us: int = Field(gt=0)
    residual_hold_us: int = Field(ge=0)
    overflow_us: int = Field(ge=0)
    fit_status: TimingFitStatus

    @model_validator(mode="after")
    def validate_math(self) -> "TimingDialogueItem":
        if self.source_end_us <= self.source_start_us:
            raise ValueError("source timing must be positive")
        if self.source_slot_duration_us != self.source_end_us - self.source_start_us:
            raise ValueError("source_slot_duration_us mismatch")
        if self.planned_speech_end_us != self.planned_speech_start_us + self.actual_speech_duration_us:
            raise ValueError("planned speech duration mismatch")
        expected_overflow = max(0, self.actual_speech_duration_us - self.source_slot_duration_us)
        expected_hold = max(0, self.source_slot_duration_us - self.actual_speech_duration_us)
        if self.overflow_us != expected_overflow or self.residual_hold_us != expected_hold:
            raise ValueError("timing fit math mismatch")
        if (expected_overflow > 0) != (self.fit_status == TimingFitStatus.OVERFLOW):
            raise ValueError("fit_status mismatch")
        return self


class ReplicaTimingPlanContent(BaseModel):
    schema_version: str = P14_TIMING_SCHEMA_VERSION
    title: str = "目标对白时序"
    target_script_artifact_id: str
    target_audio_artifact_id: str
    items: list[TimingDialogueItem] = Field(default_factory=list, max_length=20000)
    has_overflow: bool
    total_overflow_us: int = Field(ge=0)


class TimingPlanCandidateProvenance(BaseModel):
    target_script_artifact_id: str
    target_script_revision: int
    target_script_fingerprint: str
    target_audio_artifact_id: str
    target_audio_revision: int
    target_audio_fingerprint: str
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = P14_TIMING_SKILL_ID
    professional_skill_version: str
    timing_contract: str = P14_TIMING_CONTRACT
    generated_by_task_id: str
    provider_job_ids: list[str] = Field(default_factory=list, max_length=0)


class TimingPlanProvenance(TimingPlanCandidateProvenance):
    candidate_id: str
    reviewed_at: str
    review_reason: str
    supersedes_artifact_id: str | None = None


class TimingPlanCandidateRead(BaseModel):
    id: str
    project_id: str
    target_script_artifact_id: str
    target_audio_artifact_id: str
    generated_by_task_id: str | None = None
    generation_sequence: int
    input_fingerprint: str
    review_status: CandidateReviewStatus
    review_reason: str | None = None
    reviewed_at: str | None = None
    created_at: str
    content: ReplicaTimingPlanContent
    provenance: TimingPlanCandidateProvenance


class TimingPlanReviewCommand(BaseModel):
    expected_target_script_artifact_id: str
    expected_target_audio_artifact_id: str
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)


class ReplicaTimingPlanRead(BaseModel):
    project_id: str
    status: P14ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaTimingPlanContent | None = None
    provenance: TimingPlanProvenance | None = None
