from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shot_breakdown.schemas import CameraLanguage, DialogueDelivery
from app.target_assets.schemas import TargetAssetType, TargetReferenceMedia


LOCALIZED_STORYBOARD_SCHEMA_VERSION = "2.0"
ASSET_IMAGES_SCHEMA_VERSION = "2.0"
H3_PROMPT_SCHEMA_VERSION = "2.0"


class CandidateStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class _StrictProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderLocalizedCharacter(_StrictProvider):
    source_character_id: str
    localized_name: str
    identity_description_zh: str
    appearance_description_zh: str


class ProviderLocalizedScene(_StrictProvider):
    source_scene_id: str
    localized_name: str
    setting_description_zh: str
    visual_description_zh: str


class ProviderLocalizedProp(_StrictProvider):
    source_prop_id: str
    localized_name: str
    function_description_zh: str
    visual_description_zh: str


class ProviderLocalizedDialogue(_StrictProvider):
    utterance_id: str
    target_dialogue: str
    target_dialogue_zh: str


class ProviderLocalizedShot(_StrictProvider):
    shot_anchor_id: str
    localized_visual_description_zh: str
    camera_description_zh: str


class LocalizedStoryboardSemantic(_StrictProvider):
    characters: list[ProviderLocalizedCharacter] = Field(default_factory=list)
    scenes: list[ProviderLocalizedScene] = Field(default_factory=list)
    props: list[ProviderLocalizedProp] = Field(default_factory=list)
    dialogue: list[ProviderLocalizedDialogue] = Field(default_factory=list)
    shots: list[ProviderLocalizedShot] = Field(default_factory=list)


class LocalizedTargetCharacter(BaseModel):
    source_character_id: str
    target_character_id: str
    source_name: str
    display_name: str
    identity_description_zh: str
    appearance_description_zh: str


class LocalizedTargetScene(BaseModel):
    source_scene_id: str
    target_scene_id: str
    source_name: str
    display_name: str
    setting_description_zh: str
    visual_description_zh: str


class LocalizedTargetProp(BaseModel):
    source_prop_id: str
    target_prop_id: str
    source_name: str
    display_name: str
    function_description_zh: str
    visual_description_zh: str


class LocalizedStoryboardDialogue(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    source_start_us: int = Field(ge=0)
    source_end_us: int = Field(gt=0)
    source_text: str
    source_language: str | None = None
    target_character_id: str | None = None
    target_dialogue: str
    target_dialogue_zh: str


class LocalizedShotDialogueRef(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    delivery: DialogueDelivery
    target_character_id: str | None = None
    target_dialogue: str
    target_dialogue_zh: str
    overlap_start_us: int = Field(ge=0)
    overlap_end_us: int = Field(gt=0)


class LocalizedStoryboardShot(BaseModel):
    storyboard_shot_id: str
    episode_id: str
    episode_order: int = Field(ge=1)
    source_shot_anchor_id: str
    shot_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    duration_us: int = Field(gt=0)
    output_ratio: str = Field(pattern=r"^(21:9|16:9|4:3|1:1|3:4|9:16)$")
    camera_language: CameraLanguage
    source_visual_description: str
    localized_visual_description_zh: str
    camera_description_zh: str
    target_character_ids: list[str] = Field(default_factory=list)
    target_scene_ids: list[str] = Field(default_factory=list)
    target_prop_ids: list[str] = Field(default_factory=list)
    dialogue: list[LocalizedShotDialogueRef] = Field(default_factory=list)
    sound_effects: list[str] = Field(default_factory=list)
    ambience: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timing(self) -> "LocalizedStoryboardShot":
        if self.end_us <= self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("localized storyboard must preserve source shot timing")
        return self


class ReplicaLocalizedStoryboardContent(BaseModel):
    schema_version: str = LOCALIZED_STORYBOARD_SCHEMA_VERSION
    title: str = "本土化分镜表"
    source_snapshot_artifact_id: str
    target_language: str
    target_region: str
    characters: list[LocalizedTargetCharacter] = Field(default_factory=list)
    scenes: list[LocalizedTargetScene] = Field(default_factory=list)
    props: list[LocalizedTargetProp] = Field(default_factory=list)
    dialogue: list[LocalizedStoryboardDialogue] = Field(default_factory=list)
    shots: list[LocalizedStoryboardShot] = Field(min_length=1)


class PipelineProviderJobProvenance(BaseModel):
    provider_job_id: str
    provider: str
    model: str
    payload_fingerprint: str


class LocalizedStoryboardProvenance(BaseModel):
    source_snapshot_artifact_id: str
    source_snapshot_revision: int
    source_snapshot_fingerprint: str
    target_language: str
    target_region: str
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = "storyboard-localization"
    professional_skill_version: str
    provider_job: PipelineProviderJobProvenance
    provider_jobs: list[PipelineProviderJobProvenance] = Field(default_factory=list)
    generated_by_task_id: str


class LocalizedStoryboardCandidateRead(BaseModel):
    id: str
    project_id: str
    generation_sequence: int
    review_status: CandidateStatus
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    content: ReplicaLocalizedStoryboardContent
    provenance: LocalizedStoryboardProvenance


class LocalizedStoryboardRead(BaseModel):
    project_id: str
    status: ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaLocalizedStoryboardContent | None = None
    provenance: dict | None = None


class LocalizedStoryboardDialogueEdit(_StrictProvider):
    utterance_id: str = Field(min_length=1)
    target_dialogue: str = Field(min_length=1, max_length=2000)
    target_dialogue_zh: str = Field(min_length=1, max_length=2000)

    @field_validator("target_dialogue", "target_dialogue_zh")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("dialogue text cannot be blank")
        return value


class LocalizedStoryboardShotEditCommand(_StrictProvider):
    candidate_id: str | None = None
    expected_current_artifact_id: str | None = None
    expected_source_snapshot_artifact_id: str
    storyboard_shot_id: str
    localized_visual_description_zh: str = Field(min_length=1, max_length=8000)
    camera_description_zh: str = Field(min_length=1, max_length=4000)
    dialogue: list[LocalizedStoryboardDialogueEdit] = Field(default_factory=list)

    @field_validator("localized_visual_description_zh", "camera_description_zh")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("storyboard description cannot be blank")
        return value


class PipelineReviewCommand(BaseModel):
    expected_upstream_artifact_id: str
    expected_generation_sequence: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=800)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("review reason cannot be blank")
        return value


class AssetImageEntity(BaseModel):
    target_asset_id: str
    target_asset_revision: int = Field(ge=1)
    asset_type: TargetAssetType
    target_entity_id: str
    display_name: str
    review_description_zh: str
    image_prompt: str
    negative_prompt: str = ""
    prompt_review_zh: str | None = None
    image_model_id: str | None = None
    prompt_skill_id: str | None = None
    prompt_skill_version: str | None = None
    prompt_contract: str | None = None
    reference_media: list[TargetReferenceMedia] = Field(min_length=1)


class ReplicaAssetImagesContent(BaseModel):
    schema_version: str = ASSET_IMAGES_SCHEMA_VERSION
    title: str = "目标资产图"
    target_storyboard_artifact_id: str
    target_language: str
    target_region: str
    visual_style: str
    assets: list[AssetImageEntity] = Field(min_length=1)


class AssetImageProvenance(BaseModel):
    target_storyboard_artifact_id: str
    target_storyboard_revision: int
    target_storyboard_fingerprint: str
    generation_sequence: int = Field(ge=1)
    professional_skill_id: str = "asset-image-generation"
    professional_skill_version: str
    image_model_id: str | None = None
    prompt_skill_id: str | None = None
    prompt_skill_version: str | None = None
    prompt_contract: str | None = None
    prompt_provider: str | None = None
    prompt_model: str | None = None
    prompt_provider_job_ids: list[str] = Field(default_factory=list)
    provider_job_ids: list[str] = Field(default_factory=list)
    image_runtime: str
    image_model: str
    generated_by_task_id: str


class AssetImagePromptAuthoredEntity(_StrictProvider):
    target_entity_id: str = Field(min_length=1, max_length=240)
    image_prompt: str = Field(min_length=1, max_length=12000)
    negative_prompt: str = Field(default="", max_length=6000)
    review_prompt_zh: str = Field(min_length=1, max_length=6000)


class AssetImagePromptAuthoringResult(_StrictProvider):
    assets: list[AssetImagePromptAuthoredEntity] = Field(min_length=1, max_length=24)


class AssetImageCandidateRead(BaseModel):
    id: str
    project_id: str
    generation_sequence: int
    review_status: CandidateStatus
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    content: ReplicaAssetImagesContent
    provenance: AssetImageProvenance


class AssetImagesRead(BaseModel):
    project_id: str
    status: ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: ReplicaAssetImagesContent | None = None
    provenance: dict | None = None


class AssetWorkspaceGeneration(BaseModel):
    generation_id: str
    task_id: str
    created_at: datetime
    reference_media: list[TargetReferenceMedia] = Field(min_length=1)


class AssetWorkspaceEntity(BaseModel):
    target_asset_id: str
    asset_type: TargetAssetType
    target_entity_id: str
    display_name: str
    review_description_zh: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    image_prompt: str | None = None
    negative_prompt: str = ""
    prompt_review_zh: str | None = None
    image_model_id: str | None = None
    prompt_skill_id: str | None = None
    prompt_skill_version: str | None = None
    prompt_contract: str | None = None
    active_generation_id: str | None = None
    generations: list[AssetWorkspaceGeneration] = Field(default_factory=list)


class AssetWorkspaceContent(BaseModel):
    target_storyboard_artifact_id: str
    target_language: str
    target_region: str
    visual_style: str
    assets: list[AssetWorkspaceEntity] = Field(min_length=1)


class AssetWorkspaceRead(BaseModel):
    project_id: str
    status: str
    revision: int | None = None
    content: AssetWorkspaceContent | None = None


class AssetWorkspaceSelectionCommand(_StrictProvider):
    target_asset_ids: list[str] = Field(min_length=1, max_length=256)

    @field_validator("target_asset_ids")
    @classmethod
    def unique_asset_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("target_asset_ids must be non-empty and unique")
        return normalized


class H3PromptAuthoredSegment(_StrictProvider):
    generation_segment_id: str
    execution_prompt: str = Field(min_length=1, max_length=12000)
    negative_prompt: str = Field(default="", max_length=6000)
    review_prompt_zh: str = Field(min_length=1, max_length=12000)


class H3PromptAuthoringResult(_StrictProvider):
    segments: list[H3PromptAuthoredSegment] = Field(min_length=1, max_length=24)


class H3PromptProvenance(BaseModel):
    target_storyboard_artifact_id: str
    target_storyboard_revision: int
    target_storyboard_fingerprint: str
    target_assets_artifact_id: str
    target_assets_revision: int
    target_assets_fingerprint: str
    professional_skill_id: str = "minimax-h3-prompting"
    professional_skill_version: str
    model_id: str = "MiniMaxAI/MiniMax-H3"
    prompt_contract: str
    prompt_provider: str
    prompt_model: str
    provider_jobs: list[PipelineProviderJobProvenance] = Field(min_length=1)
    generated_by_task_id: str


class H3PromptsRead(BaseModel):
    project_id: str
    status: ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: dict | None = None
    provenance: H3PromptProvenance | None = None
