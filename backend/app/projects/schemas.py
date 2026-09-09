from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.projects.enums import (
    AudioPolicy,
    ProjectStatus,
    ProjectType,
    SceneStrategy,
    SourceUnderstandingProvider,
    VIDEO_PROJECT_TYPES,
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_type: ProjectType
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str = Field(min_length=1, max_length=32)
    target_region: str = Field(min_length=1, max_length=64)
    scene_strategy: SceneStrategy | None = None
    audio_policy: AudioPolicy | None = None
    visual_style: str | None = Field(default=None, max_length=80)
    source_understanding_provider: SourceUnderstandingProvider = SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API

    @model_validator(mode="after")
    def validate_source_language(self) -> "ProjectCreate":
        if self.project_type in VIDEO_PROJECT_TYPES and not self.source_language:
            raise ValueError("视频类项目必须选择原始语言")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str | None = Field(default=None, min_length=1, max_length=32)
    target_region: str | None = Field(default=None, min_length=1, max_length=64)
    scene_strategy: SceneStrategy | None = None
    audio_policy: AudioPolicy | None = None
    visual_style: str | None = Field(default=None, max_length=80)
    source_understanding_provider: SourceUnderstandingProvider | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    project_type: ProjectType
    source_language: str | None
    target_language: str
    target_region: str
    scene_strategy: SceneStrategy
    audio_policy: AudioPolicy
    visual_style: str | None
    source_understanding_provider: SourceUnderstandingProvider
    root_skill_id: str
    root_skill_version: str
    current_plan_id: str | None
    status: ProjectStatus
    workflow_revision: int
    created_at: datetime
    updated_at: datetime
