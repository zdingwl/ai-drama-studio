from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


P13_SCHEMA_VERSION = "1.0"
P13_PROMPT_VERSION = "p13-target-assets-v1"
P13_TARGET_CONTRACT = "replica-target-assets-v1"
P13_SKILL_ID = "replica-target-assets"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetAssetKind(StrEnum):
    CHARACTER = "CHARACTER"
    SCENE = "SCENE"
    PROP = "PROP"


class TargetAssetResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class TargetAssetCandidateStatus(StrEnum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class TargetAssetReference(StrictModel):
    reference_asset_id: str = Field(min_length=1, max_length=96)
    role: Literal["REFERENCE_SHEET"] = "REFERENCE_SHEET"
    media_type: Literal["image/png", "image/jpeg"]
    relative_path: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    provider_job_id: str = Field(min_length=1, max_length=36)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)


class ReplicaTargetCharacterAsset(StrictModel):
    target_asset_id: str = Field(min_length=1, max_length=96)
    asset_kind: Literal[TargetAssetKind.CHARACTER] = TargetAssetKind.CHARACTER
    asset_revision: int = Field(ge=1)
    target_character_id: str = Field(min_length=1, max_length=96)
    display_name: str = Field(min_length=1, max_length=256)
    localized_identity: str = Field(min_length=1)
    appearance_direction: str = Field(min_length=1)
    face_identity: str = Field(min_length=1)
    hair_identity: str = Field(min_length=1)
    body_silhouette: str = Field(min_length=1)
    wardrobe_baseline: str = Field(min_length=1)
    signature_features: list[str] = Field(min_length=1)
    palette_materials: list[str] = Field(min_length=1)
    continuity_constraints: list[str] = Field(min_length=1)
    generation_guidance: list[str] = Field(min_length=1)
    negative_constraints: list[str] = Field(min_length=1)
    reference_assets: list[TargetAssetReference] = Field(min_length=1)


class ReplicaTargetSceneAsset(StrictModel):
    target_asset_id: str = Field(min_length=1, max_length=96)
    asset_kind: Literal[TargetAssetKind.SCENE] = TargetAssetKind.SCENE
    asset_revision: int = Field(ge=1)
    target_scene_id: str = Field(min_length=1, max_length=96)
    display_name: str = Field(min_length=1, max_length=256)
    localized_setting: str = Field(min_length=1)
    visual_direction: str = Field(min_length=1)
    spatial_identity: str = Field(min_length=1)
    layout: str = Field(min_length=1)
    architecture_style: str = Field(min_length=1)
    materials_palette: list[str] = Field(min_length=1)
    fixed_landmarks: list[str] = Field(min_length=1)
    lighting_baseline: str = Field(min_length=1)
    time_of_day_baseline: str = Field(min_length=1)
    continuity_constraints: list[str] = Field(min_length=1)
    generation_guidance: list[str] = Field(min_length=1)
    negative_constraints: list[str] = Field(min_length=1)
    reference_assets: list[TargetAssetReference] = Field(min_length=1)


class ReplicaTargetPropAsset(StrictModel):
    target_asset_id: str = Field(min_length=1, max_length=96)
    asset_kind: Literal[TargetAssetKind.PROP] = TargetAssetKind.PROP
    asset_revision: int = Field(ge=1)
    target_prop_id: str = Field(min_length=1, max_length=96)
    display_name: str = Field(min_length=1, max_length=256)
    localized_form: str = Field(min_length=1)
    visual_form: str = Field(min_length=1)
    materials: list[str] = Field(min_length=1)
    color_palette: list[str] = Field(min_length=1)
    scale: str = Field(min_length=1)
    functional_identity: str = Field(min_length=1)
    signature_details: list[str] = Field(min_length=1)
    continuity_constraints: list[str] = Field(min_length=1)
    generation_guidance: list[str] = Field(min_length=1)
    negative_constraints: list[str] = Field(min_length=1)
    reference_assets: list[TargetAssetReference] = Field(min_length=1)


class ReplicaTargetAssetsContent(StrictModel):
    schema_version: Literal[P13_SCHEMA_VERSION] = P13_SCHEMA_VERSION
    title: str = "目标资产"
    target_bible_artifact_id: str = Field(min_length=1, max_length=36)
    target_bible_revision: int = Field(ge=1)
    target_language: str = Field(min_length=1, max_length=64)
    target_region: str = Field(min_length=1, max_length=128)
    visual_style: str = Field(min_length=1)
    global_continuity_constraints: list[str] = Field(min_length=1)
    character_assets: list[ReplicaTargetCharacterAsset]
    scene_assets: list[ReplicaTargetSceneAsset]
    prop_assets: list[ReplicaTargetPropAsset]

    @model_validator(mode="after")
    def unique_asset_ids(self) -> "ReplicaTargetAssetsContent":
        all_ids = [
            *(item.target_asset_id for item in self.character_assets),
            *(item.target_asset_id for item in self.scene_assets),
            *(item.target_asset_id for item in self.prop_assets),
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("target_asset_id must be globally unique")
        ref_ids = [
            ref.reference_asset_id
            for collection in (self.character_assets, self.scene_assets, self.prop_assets)
            for item in collection
            for ref in item.reference_assets
        ]
        if len(ref_ids) != len(set(ref_ids)):
            raise ValueError("reference_asset_id must be globally unique")
        return self


class TargetCharacterAssetSemantic(StrictModel):
    target_character_id: str
    face_identity: str = Field(min_length=1)
    hair_identity: str = Field(min_length=1)
    body_silhouette: str = Field(min_length=1)
    wardrobe_baseline: str = Field(min_length=1)
    signature_features: list[str] = Field(min_length=1)
    palette_materials: list[str] = Field(min_length=1)
    continuity_constraints: list[str] = Field(min_length=1)
    generation_guidance: list[str] = Field(min_length=1)
    negative_constraints: list[str] = Field(min_length=1)


class TargetSceneAssetSemantic(StrictModel):
    target_scene_id: str
    spatial_identity: str = Field(min_length=1)
    layout: str = Field(min_length=1)
    architecture_style: str = Field(min_length=1)
    materials_palette: list[str] = Field(min_length=1)
    fixed_landmarks: list[str] = Field(min_length=1)
    lighting_baseline: str = Field(min_length=1)
    time_of_day_baseline: str = Field(min_length=1)
    continuity_constraints: list[str] = Field(min_length=1)
    generation_guidance: list[str] = Field(min_length=1)
    negative_constraints: list[str] = Field(min_length=1)


class TargetPropAssetSemantic(StrictModel):
    target_prop_id: str
    visual_form: str = Field(min_length=1)
    materials: list[str] = Field(min_length=1)
    color_palette: list[str] = Field(min_length=1)
    scale: str = Field(min_length=1)
    functional_identity: str = Field(min_length=1)
    signature_details: list[str] = Field(min_length=1)
    continuity_constraints: list[str] = Field(min_length=1)
    generation_guidance: list[str] = Field(min_length=1)
    negative_constraints: list[str] = Field(min_length=1)


class TargetAssetsSemantic(StrictModel):
    characters: list[TargetCharacterAssetSemantic]
    scenes: list[TargetSceneAssetSemantic]
    props: list[TargetPropAssetSemantic]


class TargetAssetsProviderInput(StrictModel):
    target_language: str
    target_region: str
    target_world: dict
    visual_style: str
    global_continuity_rules: list[str]
    characters: list[dict]
    scenes: list[dict]
    props: list[dict]


class TargetAssetsProviderJobProvenance(StrictModel):
    provider_job_id: str
    provider: str
    model: str
    capability: str
    payload_fingerprint: str
    remote_job_id: str | None = None


class TargetAssetsProvenance(StrictModel):
    target_bible_artifact_id: str
    target_bible_revision: int
    target_bible_fingerprint: str
    professional_skill_id: str
    professional_skill_version: str
    schema_version: str = P13_SCHEMA_VERSION
    prompt_version: str = P13_PROMPT_VERSION
    asset_contract: str = P13_TARGET_CONTRACT
    candidate_id: str
    generated_by_task_id: str
    approved_at: datetime | None = None
    approval_method: str | None = None
    supersedes_artifact_id: str | None = None
    visual_spec_provider_profile: dict
    visual_spec_provider_job: TargetAssetsProviderJobProvenance
    image_provider_profile: dict
    image_provider_jobs: list[TargetAssetsProviderJobProvenance]


class TargetAssetsGenerateCommand(StrictModel):
    target_asset_ids: list[str] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def unique_scope(self) -> "TargetAssetsGenerateCommand":
        if len(self.target_asset_ids) != len(set(self.target_asset_ids)):
            raise ValueError("target_asset_ids cannot contain duplicates")
        return self


class TargetAssetsCandidateRead(StrictModel):
    candidate_id: str
    status: TargetAssetCandidateStatus
    target_bible_artifact_id: str
    target_bible_revision: int
    input_fingerprint: str
    scope_target_asset_ids: list[str]
    content: ReplicaTargetAssetsContent
    provenance: TargetAssetsProvenance
    published_artifact_id: str | None = None
    created_at: datetime
    approved_at: datetime | None = None


class ReplicaTargetAssetsRead(StrictModel):
    project_id: str
    status: TargetAssetResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaTargetAssetsContent | None = None
    provenance: TargetAssetsProvenance | None = None
    latest_candidate: TargetAssetsCandidateRead | None = None


class ReplicaTargetAssetsRevisionSummary(StrictModel):
    artifact_id: str
    revision: int
    validity: str
    input_fingerprint: str
    target_bible_artifact_id: str
    target_bible_revision: int
    created_at: datetime
