from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceResolutionKind(StrEnum):
    CHARACTER = "CHARACTER"
    SPEAKER = "SPEAKER"
    SCENE = "SCENE"
    PROP = "PROP"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    UNRESOLVED = "UNRESOLVED"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"


class SourceResolutionResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class ManualResolutionOperation(StrEnum):
    CONFIRM = "CONFIRM"
    MERGE = "MERGE"
    SPLIT = "SPLIT"
    MARK_UNKNOWN = "MARK_UNKNOWN"
    REASSIGN = "REASSIGN"


class _StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(_StrictProviderModel):
    ref_type: str = Field(min_length=1, max_length=48)
    ref_id: str = Field(min_length=1, max_length=160)
    episode_id: str | None = Field(default=None, max_length=80)
    shot_anchor_id: str | None = Field(default=None, max_length=80)
    utterance_id: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=400)


class EntityGroupSemantic(_StrictProviderModel):
    group_key: str = Field(min_length=1, max_length=96)
    display_name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=40)
    confidence: float = Field(ge=0.0, le=1.0)
    resolution_status: ResolutionStatus
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=500)
    notes: list[str] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def provider_status_only(self) -> "EntityGroupSemantic":
        if self.resolution_status == ResolutionStatus.MANUAL_CONFIRMED:
            raise ValueError("provider cannot emit MANUAL_CONFIRMED")
        return self


class CharacterObservationSemantic(_StrictProviderModel):
    shot_anchor_id: str
    source_candidate_id: str
    group_key: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = Field(default=None, max_length=500)


class CharacterResolutionSemantic(_StrictProviderModel):
    groups: list[EntityGroupSemantic] = Field(default_factory=list, max_length=500)
    observations: list[CharacterObservationSemantic] = Field(default_factory=list, max_length=10000)


class SpeakerGroupSemantic(EntityGroupSemantic):
    character_id: str | None = None
    source_candidate_character_ids: list[str] = Field(default_factory=list, max_length=80)


class SpeakerAttributionSemantic(_StrictProviderModel):
    utterance_id: str
    group_key: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = Field(default=None, max_length=500)


class SpeakerResolutionSemantic(_StrictProviderModel):
    groups: list[SpeakerGroupSemantic] = Field(default_factory=list, max_length=500)
    attributions: list[SpeakerAttributionSemantic] = Field(default_factory=list, max_length=10000)


class SceneAssignmentSemantic(_StrictProviderModel):
    shot_anchor_id: str
    source_candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    group_key: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = Field(default=None, max_length=500)


class SceneResolutionSemantic(_StrictProviderModel):
    groups: list[EntityGroupSemantic] = Field(default_factory=list, max_length=1000)
    assignments: list[SceneAssignmentSemantic] = Field(default_factory=list, max_length=10000)


class PropObservationSemantic(_StrictProviderModel):
    shot_anchor_id: str
    source_candidate_id: str
    group_key: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = Field(default=None, max_length=500)


class PropResolutionSemantic(_StrictProviderModel):
    groups: list[EntityGroupSemantic] = Field(default_factory=list, max_length=2000)
    observations: list[PropObservationSemantic] = Field(default_factory=list, max_length=20000)


class StableEntity(BaseModel):
    entity_id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    source_candidate_ids: list[str] = Field(default_factory=list)
    episode_ids: list[str] = Field(default_factory=list)
    shot_anchor_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    resolution_status: ResolutionStatus
    notes: list[str] = Field(default_factory=list)


class CharacterObservation(BaseModel):
    shot_anchor_id: str
    source_candidate_id: str
    character_id: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = None


class CharacterEntity(StableEntity):
    character_id: str

    @model_validator(mode="after")
    def align_id(self) -> "CharacterEntity":
        if self.entity_id != self.character_id:
            raise ValueError("character entity ids must match")
        return self


class CharacterResolutionContent(BaseModel):
    schema_version: str = "1.0"
    title: str = "人物最终归一"
    entities: list[CharacterEntity] = Field(default_factory=list)
    observations: list[CharacterObservation] = Field(default_factory=list)


class SpeakerEntity(StableEntity):
    speaker_id: str
    character_id: str | None = None
    utterance_ids: list[str] = Field(default_factory=list)
    source_candidate_character_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def align_id(self) -> "SpeakerEntity":
        if self.entity_id != self.speaker_id:
            raise ValueError("speaker entity ids must match")
        return self


class SpeakerAttribution(BaseModel):
    episode_id: str
    utterance_id: str
    utterance_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    text: str
    speaker_id: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = None


class SpeakerResolutionContent(BaseModel):
    schema_version: str = "1.0"
    title: str = "说话人最终归因"
    entities: list[SpeakerEntity] = Field(default_factory=list)
    attributions: list[SpeakerAttribution] = Field(default_factory=list)


class SceneEntity(StableEntity):
    scene_id: str
    disambiguation_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def align_id(self) -> "SceneEntity":
        if self.entity_id != self.scene_id:
            raise ValueError("scene entity ids must match")
        return self


class SceneAssignment(BaseModel):
    episode_id: str
    shot_anchor_id: str
    shot_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    source_candidate_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = None


class SceneResolutionContent(BaseModel):
    schema_version: str = "1.0"
    title: str = "场景最终归一"
    entities: list[SceneEntity] = Field(default_factory=list)
    assignments: list[SceneAssignment] = Field(default_factory=list)


class PropEntity(StableEntity):
    prop_id: str
    instance_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def align_id(self) -> "PropEntity":
        if self.entity_id != self.prop_id:
            raise ValueError("prop entity ids must match")
        return self


class PropObservation(BaseModel):
    shot_anchor_id: str
    source_candidate_id: str
    prop_id: str | None = None
    resolution_status: ResolutionStatus
    reason: str | None = None


class PropResolutionContent(BaseModel):
    schema_version: str = "1.0"
    title: str = "关键道具最终归一"
    entities: list[PropEntity] = Field(default_factory=list)
    observations: list[PropObservation] = Field(default_factory=list)


class ResolutionEpisodeInputProvenance(BaseModel):
    episode_id: str
    source_asset_sha256: str
    shot_boundary_set_id: str
    shot_boundary_fingerprint: str
    source_evidence_set_id: str
    source_evidence_fingerprint: str


class ResolutionProviderJobProvenance(BaseModel):
    provider_job_id: str
    provider: str
    model: str
    capability: str
    professional_skill_id: str
    payload_fingerprint: str
    remote_job_id: str | None = None


class ManualAdjudicationProvenance(BaseModel):
    mode: Literal["MANUAL"] = "MANUAL"
    operation: ManualResolutionOperation
    reason: str


class SourceResolutionProvenance(BaseModel):
    resolution_kind: SourceResolutionKind
    source_video_artifact_id: str
    source_video_fingerprint: str
    source_bible_artifact_id: str
    source_bible_fingerprint: str
    source_shot_facts_artifact_id: str
    source_shot_facts_fingerprint: str
    shot_anchors_artifact_id: str
    shot_anchors_fingerprint: str
    source_dialogue_artifact_id: str | None = None
    source_dialogue_fingerprint: str | None = None
    source_characters_artifact_id: str | None = None
    source_characters_fingerprint: str | None = None
    episode_inputs: list[ResolutionEpisodeInputProvenance] = Field(default_factory=list)
    provider_jobs: list[ResolutionProviderJobProvenance] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    schema_version: str
    professional_skill_id: str
    professional_skill_version: str
    source_truth_contract: str
    generated_by_task_id: str | None = None
    supersedes_artifact_id: str | None = None
    adjudication: ManualAdjudicationProvenance | None = None


class CharacterResolutionRead(BaseModel):
    status: SourceResolutionResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: CharacterResolutionContent | None = None
    provenance: SourceResolutionProvenance | None = None


class SpeakerResolutionRead(BaseModel):
    status: SourceResolutionResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: SpeakerResolutionContent | None = None
    provenance: SourceResolutionProvenance | None = None


class SceneResolutionRead(BaseModel):
    status: SourceResolutionResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: SceneResolutionContent | None = None
    provenance: SourceResolutionProvenance | None = None


class PropResolutionRead(BaseModel):
    status: SourceResolutionResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: PropResolutionContent | None = None
    provenance: SourceResolutionProvenance | None = None


class SourceResolutionRead(BaseModel):
    project_id: str
    characters: CharacterResolutionRead
    speakers: SpeakerResolutionRead
    scenes: SceneResolutionRead
    props: PropResolutionRead


class SourceResolutionRevisionSummary(BaseModel):
    resolution_kind: SourceResolutionKind
    artifact_id: str
    revision: int
    status: SourceResolutionResultStatus
    input_fingerprint: str
    created_at: str
    supersedes_artifact_id: str | None = None
    adjudication: ManualAdjudicationProvenance | None = None


class ManualResolutionCommand(BaseModel):
    expected_revision: int = Field(ge=1)
    operation: ManualResolutionOperation
    entity_ids: list[str] = Field(default_factory=list, max_length=100)
    target_entity_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list, max_length=10000)
    split_groups: list[list[str]] = Field(default_factory=list, max_length=100)
    character_id: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=1000)
