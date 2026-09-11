from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


P12_SCHEMA_VERSION = "1.0"
P12_PROMPT_VERSION = "p12-target-script-localization-v1"
P12_TARGET_CONTRACT = "replica-target-script-localization-v1"
P12_SOURCE_DIALOGUE_CONTRACT = "p6-canonical-dialogue-frozen-in-p10-v1"
P12_SKILL_ID = "target-script-localization"


class TargetScriptResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class _StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderLocalizedDialogue(_StrictProviderModel):
    utterance_id: str = Field(min_length=1, max_length=160)
    translation_text: str = Field(min_length=1, max_length=4000)
    localization_text: str = Field(min_length=1, max_length=4000)
    final_target_dialogue: str = Field(min_length=1, max_length=4000)
    localization_notes: list[str] = Field(default_factory=list, max_length=40)


class TargetScriptSemantic(_StrictProviderModel):
    dialogue: list[ProviderLocalizedDialogue] = Field(default_factory=list, max_length=20000)


class TargetScriptDialogueLine(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    source_start_us: int = Field(ge=0)
    source_end_us: int = Field(gt=0)
    source_text: str
    source_language: str | None = None
    target_character_id: str | None = None
    translation_text: str
    localization_text: str
    final_target_dialogue: str
    localization_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_time(self) -> "TargetScriptDialogueLine":
        if self.source_end_us <= self.source_start_us:
            raise ValueError("Target Script source dialogue time must preserve Source Snapshot timing")
        return self


class TargetScriptEpisode(BaseModel):
    episode_id: str
    episode_order: int = Field(ge=1)
    dialogue: list[TargetScriptDialogueLine] = Field(default_factory=list)


class ReplicaTargetScriptContent(BaseModel):
    schema_version: str = P12_SCHEMA_VERSION
    title: str = "目标剧本与对白"
    target_language: str
    target_region: str
    source_snapshot_artifact_id: str
    adaptation_plan_artifact_id: str
    target_bible_artifact_id: str
    episodes: list[TargetScriptEpisode] = Field(default_factory=list)


class TargetScriptProviderJobProvenance(BaseModel):
    provider_job_id: str
    provider: str
    model: str
    capability: str
    professional_skill_id: str
    payload_fingerprint: str
    remote_job_id: str | None = None


class TargetScriptProvenance(BaseModel):
    source_snapshot_artifact_id: str
    source_snapshot_revision: int
    source_snapshot_fingerprint: str
    adaptation_plan_artifact_id: str
    adaptation_plan_revision: int
    adaptation_plan_fingerprint: str
    target_bible_artifact_id: str
    target_bible_revision: int
    target_bible_fingerprint: str
    target_language: str
    target_region: str
    professional_skill_id: str = P12_SKILL_ID
    professional_skill_version: str
    provider: str
    model: str
    provider_job: TargetScriptProviderJobProvenance
    prompt_version: str = P12_PROMPT_VERSION
    schema_version: str = P12_SCHEMA_VERSION
    target_contract: str = P12_TARGET_CONTRACT
    source_dialogue_contract: str = P12_SOURCE_DIALOGUE_CONTRACT
    generated_by_task_id: str
    supersedes_artifact_id: str | None = None


class ReplicaTargetScriptRead(BaseModel):
    project_id: str
    status: TargetScriptResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaTargetScriptContent | None = None
    provenance: TargetScriptProvenance | None = None


class ReplicaTargetScriptRevisionSummary(BaseModel):
    artifact_id: str
    revision: int
    validity: str
    input_fingerprint: str
    source_snapshot_artifact_id: str
    adaptation_plan_artifact_id: str
    target_bible_artifact_id: str
    created_at: str
