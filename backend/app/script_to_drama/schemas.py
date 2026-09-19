"""Independent script-to-drama preproduction data contracts (not Replica P11/P15)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class VisualEntity(Strict):
    name: str = Field(min_length=1, max_length=160)
    visual_description: str = Field(min_length=1, max_length=1200)
    source_evidence: str = Field(min_length=1, max_length=200)
    source_fact: str = Field(default="", max_length=600)
    visual_inference: str = Field(default="", max_length=600)


class WorldChunk(Strict):
    characters: list[VisualEntity] = Field(default_factory=list)
    locations: list[VisualEntity] = Field(default_factory=list)
    props: list[VisualEntity] = Field(default_factory=list)
    unresolved_decisions: list[str] = Field(default_factory=list)


class DirectedShot(Strict):
    source_quote: str = Field(min_length=1, max_length=200)
    narrative_beat: str = Field(min_length=1, max_length=1200)
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str = Field(min_length=1, max_length=80)
    prop_ids: list[str] = Field(default_factory=list)
    shot_size: str = Field(min_length=1, max_length=120)
    camera_angle: str = Field(min_length=1, max_length=120)
    composition: str = Field(min_length=1, max_length=600)
    camera_motion: str = Field(min_length=1, max_length=300)
    visible_action: str = Field(min_length=1, max_length=1200)
    dialogue_or_voiceover: str = Field(default="", max_length=1400)
    estimated_seconds: float = Field(gt=0, le=30)
    continuity_notes: str = Field(default="", max_length=800)


class StoryboardChunk(Strict):
    shots: list[DirectedShot] = Field(min_length=1, max_length=120)
    unresolved_decisions: list[str] = Field(default_factory=list)


class StageRead(BaseModel):
    status: ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    content: dict | None = None


class ScriptToDramaState(BaseModel):
    project_id: str
    analysis: StageRead
    world: StageRead
    assets: StageRead
    storyboard: StageRead
    asset_images: StageRead
    prompts: StageRead
    generated_video: StageRead
    selection: StageRead
    final_output: StageRead
    video_runtime_status: str = "PRODUCTION_PIPELINE_CONNECTED"


class AssetPromptItem(Strict):
    target_entity_id: str = Field(min_length=1, max_length=120)
    image_prompt: str = Field(min_length=1, max_length=12000)
    negative_prompt: str = Field(default="", max_length=6000)
    review_prompt_zh: str = Field(min_length=1, max_length=6000)


class AssetPromptBatch(Strict):
    assets: list[AssetPromptItem] = Field(min_length=1, max_length=24)


class AssetMedia(Strict):
    reference_id: str
    role: str
    storage_relpath: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: str = "image/png"


class GeneratedAsset(Strict):
    target_asset_id: str
    target_entity_id: str
    asset_type: str
    display_name: str
    image_prompt: str
    negative_prompt: str = ""
    review_prompt_zh: str
    media: list[AssetMedia] = Field(min_length=1)


class H3PromptItem(Strict):
    generation_segment_id: str
    execution_prompt: str = Field(min_length=1, max_length=12000)
    negative_prompt: str = Field(default="", max_length=6000)
    review_prompt_zh: str = Field(min_length=1, max_length=12000)


class H3PromptBatch(Strict):
    segments: list[H3PromptItem] = Field(min_length=1, max_length=24)


class GeneratedClip(Strict):
    generation_segment_id: str
    storage_relpath: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = "video/mp4"
    duration_us: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    codec_name: str
    provider_job_id: str
    remote_job_id: str | None = None


class SelectionCommand(BaseModel):
    expected_generated_video_artifact_id: str = Field(min_length=1, max_length=160)
    selected_segment_ids: list[str] = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=800)
