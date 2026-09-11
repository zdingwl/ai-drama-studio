from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


P11_SCHEMA_VERSION = "1.0"
P11_PROMPT_VERSION = "p11-replica-target-bible-v1"
P11_TARGET_CONTRACT = "replica-target-bible-v1"
P11_PRESERVATION_CONTRACT = "replica-story-rhythm-locks-v1"
P11_SKILL_ID = "replica-target-bible"


class TargetBibleArtifactKind(StrEnum):
    ADAPTATION_PLAN = "ADAPTATION_PLAN"
    TARGET_BIBLE = "TARGET_BIBLE"


class TargetBibleResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class LocalizationCategory(StrEnum):
    CHARACTER = "CHARACTER"
    SCENE = "SCENE"
    PROP = "PROP"
    CULTURE = "CULTURE"
    ADDRESSING = "ADDRESSING"
    WORLD = "WORLD"
    VISUAL_STYLE = "VISUAL_STYLE"


class PreservationCategory(StrEnum):
    STORY_MAINLINE = "STORY_MAINLINE"
    HOOK = "HOOK"
    CONFLICT = "CONFLICT"
    REVERSAL = "REVERSAL"
    INFORMATION_REVEAL = "INFORMATION_REVEAL"
    EMOTIONAL_PEAK = "EMOTIONAL_PEAK"
    PAYOFF = "PAYOFF"
    CLIFFHANGER = "CLIFFHANGER"
    STORY_BEAT_TIMING = "STORY_BEAT_TIMING"
    SHOT_RHYTHM = "SHOT_RHYTHM"
    SCENE_ORDER = "SCENE_ORDER"
    SHOT_LOGIC = "SHOT_LOGIC"
    ACTION_RHYTHM = "ACTION_RHYTHM"


class _StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderLocalizationDecision(_StrictProviderModel):
    category: LocalizationCategory
    source_ref: str | None = Field(default=None, max_length=160)
    source_value: str = Field(min_length=1, max_length=800)
    target_value: str = Field(min_length=1, max_length=1200)
    reason: str = Field(min_length=1, max_length=800)


class ProviderTargetWorld(_StrictProviderModel):
    setting_summary: str = Field(min_length=1, max_length=2500)
    cultural_context: str = Field(min_length=1, max_length=2500)
    social_context: str = Field(min_length=1, max_length=2500)
    localization_principles: list[str] = Field(min_length=1, max_length=40)


class ProviderTargetCharacter(_StrictProviderModel):
    source_character_id: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    localized_identity: str = Field(min_length=1, max_length=1200)
    appearance_direction: str = Field(min_length=1, max_length=1200)
    personality_constraints: list[str] = Field(default_factory=list, max_length=40)
    continuity_rules: list[str] = Field(default_factory=list, max_length=40)
    reason: str = Field(min_length=1, max_length=800)


class ProviderTargetScene(_StrictProviderModel):
    source_scene_id: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    localized_setting: str = Field(min_length=1, max_length=1500)
    visual_direction: str = Field(min_length=1, max_length=1500)
    continuity_rules: list[str] = Field(default_factory=list, max_length=40)
    reason: str = Field(min_length=1, max_length=800)


class ProviderTargetProp(_StrictProviderModel):
    source_prop_id: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    localized_form: str = Field(min_length=1, max_length=1200)
    continuity_rules: list[str] = Field(default_factory=list, max_length=40)
    reason: str = Field(min_length=1, max_length=800)


class ReplicaTargetBibleSemantic(_StrictProviderModel):
    target_world: ProviderTargetWorld
    characters: list[ProviderTargetCharacter] = Field(default_factory=list, max_length=500)
    scenes: list[ProviderTargetScene] = Field(default_factory=list, max_length=1000)
    props: list[ProviderTargetProp] = Field(default_factory=list, max_length=2000)
    visual_style: str = Field(min_length=1, max_length=1800)
    continuity_rules: list[str] = Field(default_factory=list, max_length=100)
    dialogue_style_rules: list[str] = Field(default_factory=list, max_length=100)
    adaptation_summary: str = Field(min_length=1, max_length=2500)
    localization_decisions: list[ProviderLocalizationDecision] = Field(default_factory=list, max_length=500)


class PreservationLock(BaseModel):
    lock_id: str
    category: PreservationCategory
    source_summary: str
    source_refs: list[str] = Field(default_factory=list)
    constraint: str


class LocalizationDecision(BaseModel):
    decision_id: str
    category: LocalizationCategory
    source_ref: str | None = None
    source_value: str
    target_value: str
    reason: str


class ReplicaAdaptationPlanContent(BaseModel):
    schema_version: str = P11_SCHEMA_VERSION
    title: str = "复刻本土化方案"
    target_language: str
    target_region: str
    source_snapshot_artifact_id: str
    preservation_locks: list[PreservationLock] = Field(default_factory=list)
    localization_decisions: list[LocalizationDecision] = Field(default_factory=list)
    dialogue_localization_strategy: list[str] = Field(default_factory=list)
    scene_strategy: str
    visual_style: str


class ReplicaTargetWorld(BaseModel):
    setting_summary: str
    cultural_context: str
    social_context: str
    localization_principles: list[str] = Field(default_factory=list)


class ReplicaTargetCharacter(BaseModel):
    target_character_id: str
    source_character_id: str
    source_display_name: str
    display_name: str
    localized_identity: str
    appearance_direction: str
    personality_constraints: list[str] = Field(default_factory=list)
    continuity_rules: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def target_identity_is_distinct(self) -> "ReplicaTargetCharacter":
        if self.target_character_id == self.source_character_id:
            raise ValueError("Target Character id must be distinct from Source Character id")
        return self


class ReplicaTargetScene(BaseModel):
    target_scene_id: str
    source_scene_id: str
    source_display_name: str
    display_name: str
    localized_setting: str
    visual_direction: str
    continuity_rules: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def target_identity_is_distinct(self) -> "ReplicaTargetScene":
        if self.target_scene_id == self.source_scene_id:
            raise ValueError("Target Scene id must be distinct from Source Scene id")
        return self


class ReplicaTargetProp(BaseModel):
    target_prop_id: str
    source_prop_id: str
    source_display_name: str
    display_name: str
    localized_form: str
    continuity_rules: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def target_identity_is_distinct(self) -> "ReplicaTargetProp":
        if self.target_prop_id == self.source_prop_id:
            raise ValueError("Target Prop id must be distinct from Source Prop id")
        return self


class ReplicaTargetBibleContent(BaseModel):
    schema_version: str = P11_SCHEMA_VERSION
    title: str = "复刻目标设定"
    target_language: str
    target_region: str
    source_snapshot_artifact_id: str
    target_world: ReplicaTargetWorld
    characters: list[ReplicaTargetCharacter] = Field(default_factory=list)
    scenes: list[ReplicaTargetScene] = Field(default_factory=list)
    props: list[ReplicaTargetProp] = Field(default_factory=list)
    visual_style: str
    continuity_rules: list[str] = Field(default_factory=list)
    dialogue_style_rules: list[str] = Field(default_factory=list)
    adaptation_summary: str


class TargetBibleProviderJobProvenance(BaseModel):
    provider_job_id: str
    provider: str
    model: str
    capability: str
    professional_skill_id: str
    payload_fingerprint: str
    remote_job_id: str | None = None


class ReplicaTargetProvenance(BaseModel):
    artifact_kind: TargetBibleArtifactKind
    source_snapshot_artifact_id: str
    source_snapshot_revision: int
    source_snapshot_fingerprint: str
    target_language: str
    target_region: str
    scene_strategy: str
    visual_style: str | None = None
    professional_skill_id: str = P11_SKILL_ID
    professional_skill_version: str
    provider: str
    model: str
    provider_job: TargetBibleProviderJobProvenance
    prompt_version: str = P11_PROMPT_VERSION
    schema_version: str = P11_SCHEMA_VERSION
    target_contract: str = P11_TARGET_CONTRACT
    preservation_contract: str = P11_PRESERVATION_CONTRACT
    generated_by_task_id: str
    supersedes_artifact_id: str | None = None


class ReplicaTargetArtifactRead(BaseModel):
    status: TargetBibleResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaAdaptationPlanContent | ReplicaTargetBibleContent | None = None
    provenance: ReplicaTargetProvenance | None = None


class ReplicaTargetBibleRead(BaseModel):
    project_id: str
    status: TargetBibleResultStatus
    source_snapshot_artifact_id: str | None = None
    source_snapshot_revision: int | None = None
    adaptation_plan: ReplicaTargetArtifactRead
    target_bible: ReplicaTargetArtifactRead


class ReplicaTargetBibleRevisionSummary(BaseModel):
    artifact_kind: TargetBibleArtifactKind
    artifact_id: str
    revision: int
    validity: str
    input_fingerprint: str
    source_snapshot_artifact_id: str
    created_at: str
