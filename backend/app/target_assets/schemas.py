from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


P13_SCHEMA_VERSION = "1.0"
P13_PROMPT_VERSION = "p13-replica-target-assets-v3"
P13_TARGET_ASSET_CONTRACT = "replica-target-visual-identity-v2"
P13_ENTITY_BINDING_CONTRACT = "target-bible-entity-binding-v1"
P13_REVIEW_CONTRACT = "human-target-asset-approval-v1"
P13_SKILL_ID = "replica-target-assets"


class TargetAssetType(StrEnum):
    CHARACTER = "CHARACTER"
    SCENE = "SCENE"
    PROP = "PROP"


class TargetAssetsResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class CandidateReviewStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ReferenceMediaRole(StrEnum):
    FACE = "FACE"
    FULL_BODY = "FULL_BODY"
    WARDROBE = "WARDROBE"
    LAYOUT = "LAYOUT"
    LANDMARK = "LANDMARK"
    DETAIL = "DETAIL"
    OTHER = "OTHER"


class _StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderCharacterAssetSemantic(_StrictProviderModel):
    target_character_id: str = Field(min_length=1, max_length=160)
    demographic_direction: str = Field(min_length=1, max_length=1200)
    face_direction: str = Field(min_length=1, max_length=1200)
    hair_direction: str = Field(min_length=1, max_length=1200)
    body_direction: str = Field(min_length=1, max_length=1200)
    wardrobe_baseline: str = Field(min_length=1, max_length=1600)
    signature_visual_features: list[str] = Field(min_length=1, max_length=40)
    continuity_constraints: list[str] = Field(min_length=1, max_length=60)
    generation_guidance: list[str] = Field(min_length=1, max_length=60)
    negative_constraints: list[str] = Field(min_length=1, max_length=60)


class ProviderSceneAssetSemantic(_StrictProviderModel):
    target_scene_id: str = Field(min_length=1, max_length=160)
    layout: str = Field(min_length=1, max_length=1800)
    architecture_style: str = Field(min_length=1, max_length=1400)
    interior_exterior_style: str = Field(min_length=1, max_length=1400)
    materials_palette: list[str] = Field(min_length=1, max_length=50)
    fixed_landmarks: list[str] = Field(min_length=1, max_length=50)
    lighting_baseline: str = Field(min_length=1, max_length=1200)
    time_of_day_baseline: str = Field(min_length=1, max_length=800)
    continuity_constraints: list[str] = Field(min_length=1, max_length=60)
    generation_guidance: list[str] = Field(min_length=1, max_length=60)
    negative_constraints: list[str] = Field(min_length=1, max_length=60)


class ProviderPropAssetSemantic(_StrictProviderModel):
    target_prop_id: str = Field(min_length=1, max_length=160)
    visual_form: str = Field(min_length=1, max_length=1400)
    materials: list[str] = Field(min_length=1, max_length=40)
    color_palette: list[str] = Field(min_length=1, max_length=40)
    scale_reference: str = Field(min_length=1, max_length=900)
    signature_visual_features: list[str] = Field(min_length=1, max_length=40)
    continuity_constraints: list[str] = Field(min_length=1, max_length=60)
    generation_guidance: list[str] = Field(min_length=1, max_length=60)
    negative_constraints: list[str] = Field(min_length=1, max_length=60)


class TargetAssetsSemantic(_StrictProviderModel):
    characters: list[ProviderCharacterAssetSemantic] = Field(default_factory=list, max_length=500)
    scenes: list[ProviderSceneAssetSemantic] = Field(default_factory=list, max_length=1000)
    props: list[ProviderPropAssetSemantic] = Field(default_factory=list, max_length=2000)


class TargetReferenceMedia(BaseModel):
    reference_id: str = Field(min_length=1, max_length=160)
    role: ReferenceMediaRole
    uri: str = Field(min_length=1, max_length=2000)
    mime_type: str = Field(min_length=1, max_length=120)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    provider_job_id: str = Field(min_length=1, max_length=160)


class TargetCharacterAsset(BaseModel):
    target_asset_id: str
    target_asset_revision: int = Field(ge=1)
    asset_type: TargetAssetType = TargetAssetType.CHARACTER
    target_entity_id: str
    target_character_id: str
    display_name: str
    asset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_direction: str
    demographic_direction: str
    face_direction: str
    hair_direction: str
    body_direction: str
    wardrobe_baseline: str
    signature_visual_features: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    generation_guidance: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    reference_media: list[TargetReferenceMedia] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entity_binding(self) -> "TargetCharacterAsset":
        if self.asset_type != TargetAssetType.CHARACTER or self.target_entity_id != self.target_character_id:
            raise ValueError("Character asset target entity binding is invalid")
        return self


class TargetSceneAsset(BaseModel):
    target_asset_id: str
    target_asset_revision: int = Field(ge=1)
    asset_type: TargetAssetType = TargetAssetType.SCENE
    target_entity_id: str
    target_scene_id: str
    display_name: str
    asset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    spatial_identity: str
    layout: str
    architecture_style: str
    interior_exterior_style: str
    materials_palette: list[str] = Field(default_factory=list)
    fixed_landmarks: list[str] = Field(default_factory=list)
    lighting_baseline: str
    time_of_day_baseline: str
    continuity_constraints: list[str] = Field(default_factory=list)
    generation_guidance: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    reference_media: list[TargetReferenceMedia] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entity_binding(self) -> "TargetSceneAsset":
        if self.asset_type != TargetAssetType.SCENE or self.target_entity_id != self.target_scene_id:
            raise ValueError("Scene asset target entity binding is invalid")
        return self


class TargetPropAsset(BaseModel):
    target_asset_id: str
    target_asset_revision: int = Field(ge=1)
    asset_type: TargetAssetType = TargetAssetType.PROP
    target_entity_id: str
    target_prop_id: str
    display_name: str
    asset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    functional_identity: str
    visual_form: str
    materials: list[str] = Field(default_factory=list)
    color_palette: list[str] = Field(default_factory=list)
    scale_reference: str
    signature_visual_features: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    generation_guidance: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    reference_media: list[TargetReferenceMedia] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entity_binding(self) -> "TargetPropAsset":
        if self.asset_type != TargetAssetType.PROP or self.target_entity_id != self.target_prop_id:
            raise ValueError("Prop asset target entity binding is invalid")
        return self


class ReplicaTargetAssetsContent(BaseModel):
    schema_version: str = P13_SCHEMA_VERSION
    title: str = "目标资产"
    target_bible_artifact_id: str
    target_language: str
    target_region: str
    visual_style: str
    characters: list[TargetCharacterAsset] = Field(default_factory=list)
    scenes: list[TargetSceneAsset] = Field(default_factory=list)
    props: list[TargetPropAsset] = Field(default_factory=list)


class TargetAssetsProviderJobProvenance(BaseModel):
    provider_job_id: str
    provider: str
    model: str
    capability: str
    professional_skill_id: str
    payload_fingerprint: str
    remote_job_id: str | None = None


class TargetAssetsCandidateProvenance(BaseModel):
    target_bible_artifact_id: str
    target_bible_revision: int
    target_bible_fingerprint: str
    base_target_assets_artifact_id: str | None = None
    target_language: str
    target_region: str
    generation_sequence: int = Field(ge=1)
    generation_base_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    professional_skill_id: str = P13_SKILL_ID
    professional_skill_version: str
    provider: str
    model: str
    provider_job: TargetAssetsProviderJobProvenance
    prompt_version: str = P13_PROMPT_VERSION
    schema_version: str = P13_SCHEMA_VERSION
    target_asset_contract: str = P13_TARGET_ASSET_CONTRACT
    entity_binding_contract: str = P13_ENTITY_BINDING_CONTRACT
    review_contract: str = P13_REVIEW_CONTRACT
    generated_by_task_id: str


class TargetAssetsProvenance(TargetAssetsCandidateProvenance):
    candidate_id: str
    reviewed_by: str = "USER_EXPLICIT_ACTION"
    reviewed_at: datetime
    review_reason: str
    supersedes_artifact_id: str | None = None


class TargetAssetsCandidateRead(BaseModel):
    id: str
    project_id: str
    target_bible_artifact_id: str
    base_target_assets_artifact_id: str | None = None
    generated_by_task_id: str | None = None
    generation_sequence: int
    input_fingerprint: str
    schema_version: str
    review_status: CandidateReviewStatus
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    content: ReplicaTargetAssetsContent
    provenance: TargetAssetsCandidateProvenance


class ReplicaTargetAssetsRead(BaseModel):
    project_id: str
    status: TargetAssetsResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaTargetAssetsContent | None = None
    provenance: TargetAssetsProvenance | None = None


class ReplicaTargetAssetsRevisionSummary(BaseModel):
    artifact_id: str
    revision: int
    validity: str
    input_fingerprint: str
    target_bible_artifact_id: str
    candidate_id: str
    created_at: str


class TargetAssetsReviewCommand(BaseModel):
    expected_target_bible_artifact_id: str = Field(min_length=1, max_length=160)
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("review reason must not be blank")
        return normalized


class TargetAssetRef(BaseModel):
    target_assets_artifact_id: str
    target_asset_id: str
    target_asset_revision: int = Field(ge=1)
    asset_type: TargetAssetType
    target_entity_id: str
