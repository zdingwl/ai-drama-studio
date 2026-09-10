from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.projects.enums import ProjectType


class Capability(StrEnum):
    SOURCE_VIDEO_INGEST = "SOURCE_VIDEO_INGEST"
    SOURCE_TEXT_INGEST = "SOURCE_TEXT_INGEST"
    MEDIA_PREFLIGHT = "MEDIA_PREFLIGHT"
    SHOT_BOUNDARY = "SHOT_BOUNDARY"
    SOURCE_DIALOGUE_EVIDENCE = "SOURCE_DIALOGUE_EVIDENCE"
    EPISODE_UNDERSTANDING = "EPISODE_UNDERSTANDING"
    STORY_RHYTHM = "STORY_RHYTHM"
    SHOT_BREAKDOWN = "SHOT_BREAKDOWN"
    IDENTITY_RESOLUTION = "IDENTITY_RESOLUTION"
    SCENE_RESOLUTION = "SCENE_RESOLUTION"
    PROP_RESOLUTION = "PROP_RESOLUTION"
    SOURCE_SNAPSHOT = "SOURCE_SNAPSHOT"
    SCRIPT_ANALYSIS = "SCRIPT_ANALYSIS"
    NOVEL_ADAPTATION = "NOVEL_ADAPTATION"
    LOCALIZATION = "LOCALIZATION"
    TARGET_BIBLE = "TARGET_BIBLE"
    TARGET_SCRIPT = "TARGET_SCRIPT"
    TARGET_ASSETS = "TARGET_ASSETS"
    TTS = "TTS"
    TIMING = "TIMING"
    STORYBOARD = "STORYBOARD"
    VIDEO_GENERATION = "VIDEO_GENERATION"
    QC_SELECTION = "QC_SELECTION"
    LIP_SYNC = "LIP_SYNC"
    POST_PRODUCTION = "POST_PRODUCTION"
    EXPORT_SCRIPT = "EXPORT_SCRIPT"


class CapabilityAvailability(StrEnum):
    PLANNED = "PLANNED"
    AVAILABLE = "AVAILABLE"


class ArtifactType(StrEnum):
    SOURCE_VIDEO = "SOURCE_VIDEO"
    SOURCE_TEXT = "SOURCE_TEXT"
    SHOT_ANCHORS = "SHOT_ANCHORS"
    SOURCE_DIALOGUE = "SOURCE_DIALOGUE"
    SOURCE_BIBLE = "SOURCE_BIBLE"
    STORY_SKELETON = "STORY_SKELETON"
    RHYTHM_SKELETON = "RHYTHM_SKELETON"
    SOURCE_SHOT_FACTS = "SOURCE_SHOT_FACTS"
    SOURCE_CHARACTERS = "SOURCE_CHARACTERS"
    SOURCE_SPEAKERS = "SOURCE_SPEAKERS"
    SOURCE_SCENES = "SOURCE_SCENES"
    SOURCE_PROPS = "SOURCE_PROPS"
    SOURCE_VIDEO_SNAPSHOT = "SOURCE_VIDEO_SNAPSHOT"
    SOURCE_TEXT_SNAPSHOT = "SOURCE_TEXT_SNAPSHOT"
    ADAPTATION_PLAN = "ADAPTATION_PLAN"
    TARGET_BIBLE = "TARGET_BIBLE"
    TARGET_SCRIPT = "TARGET_SCRIPT"
    TARGET_ASSETS = "TARGET_ASSETS"
    TARGET_AUDIO = "TARGET_AUDIO"
    TIMING_PLAN = "TIMING_PLAN"
    TARGET_STORYBOARD = "TARGET_STORYBOARD"
    GENERATION_SEGMENTS = "GENERATION_SEGMENTS"
    GENERATED_VIDEO = "GENERATED_VIDEO"
    GENERATION_SELECTION = "GENERATION_SELECTION"
    FINAL_OUTPUT = "FINAL_OUTPUT"


class CapabilityDefinition(BaseModel):
    id: Capability
    title: str
    description: str
    category: str
    availability: CapabilityAvailability = CapabilityAvailability.PLANNED


class SkillStepDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    phase: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=800)
    capabilities: tuple[Capability, ...]
    requires: tuple[ArtifactType, ...] = ()
    produces: tuple[ArtifactType, ...] = ()


class SkillManifest(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    category: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=800)
    project_type: ProjectType
    when_to_use: tuple[str, ...]
    when_not_to_use: tuple[str, ...]
    required_inputs: tuple[ArtifactType, ...]
    readable_artifacts: tuple[ArtifactType, ...]
    required_capabilities: tuple[Capability, ...]
    subskills: tuple[str, ...]
    manual_path: str = Field(min_length=1, max_length=240)
    steps: tuple[SkillStepDefinition, ...]
    user_decision_policy: tuple[str, ...]
    auto_decision_policy: tuple[str, ...]
    output_contracts: tuple[ArtifactType, ...]
    completion_criteria: tuple[str, ...]
    failure_policy: tuple[str, ...]
    next_recommended_skills: tuple[str, ...]

    @model_validator(mode="after")
    def validate_manifest(self) -> "SkillManifest":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Skill step id 不能重复")

        declared = set(self.required_capabilities)
        used = {capability for step in self.steps for capability in step.capabilities}
        missing = used - declared
        if missing:
            raise ValueError(f"Skill step 使用了未声明 capability: {sorted(item.value for item in missing)}")

        if not self.steps:
            raise ValueError("Root Skill 必须至少包含一个执行步骤")
        return self

    @property
    def title(self) -> str:
        return self.name

    @property
    def purpose(self) -> str:
        return self.description


RootSkillDefinition = SkillManifest


class RootSkillDetail(SkillManifest):
    manual: str
