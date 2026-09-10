from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class SourceAnalysisState(StrEnum):
    NOT_READY = "NOT_READY"
    RUNNING = "RUNNING"
    READY = "READY"
    NEEDS_REFRESH = "NEEDS_REFRESH"
    FAILED = "FAILED"


class SourceAnalysisStatusRead(BaseModel):
    project_id: str
    state: SourceAnalysisState
    progress_percent: int = Field(default=0, ge=0, le=100)
    current_stage: str | None = None
    task_id: str | None = None
    can_retry: bool = False
    message: str


class SourceScriptDialogue(BaseModel):
    utterance_id: str
    utterance_number: int
    start_us: int
    end_us: int
    speaker_id: str | None = None
    speaker_name: str
    text: str
    delivery: str


class SourceScriptShot(BaseModel):
    episode_id: str
    shot_anchor_id: str
    shot_number: int
    start_us: int
    end_us: int
    duration_us: int
    action_summary: str
    visual_description: str
    shot_size: str
    composition: str
    angle_or_type: str
    movement: str
    focal_length_dof: str
    thumbnail_url: str
    reference_clip_url: str
    dialogues: list[SourceScriptDialogue] = Field(default_factory=list)


class SourceScriptScene(BaseModel):
    scene_number: int
    episode_id: str
    scene_id: str | None = None
    scene_name: str
    start_us: int
    end_us: int
    character_names: list[str] = Field(default_factory=list)
    shots: list[SourceScriptShot] = Field(default_factory=list)


class SourceScriptEntity(BaseModel):
    id: str
    name: str


class SourceScriptRead(BaseModel):
    project_id: str
    state: SourceAnalysisState
    title: str
    scenes: list[SourceScriptScene] = Field(default_factory=list)
    characters: list[SourceScriptEntity] = Field(default_factory=list)
    props: list[SourceScriptEntity] = Field(default_factory=list)


class StoryboardDraftStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class StoryboardShotOverride(BaseModel):
    shot_anchor_id: str
    visual_description: str = Field(min_length=1, max_length=4000)
    shot_size: str = Field(max_length=240)
    composition: str = Field(max_length=1000)
    angle_or_type: str = Field(max_length=400)
    movement: str = Field(max_length=800)
    focal_length_dof: str = Field(max_length=800)


class StoryboardDraftRead(BaseModel):
    project_id: str
    status: StoryboardDraftStatus
    revision: int | None = None
    base_source_current: bool
    overrides: list[StoryboardShotOverride] = Field(default_factory=list)


class StoryboardShotEditCommand(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    shot_anchor_id: str = Field(min_length=1, max_length=64)
    reset_to_source: bool = False
    visual_description: str | None = Field(default=None, min_length=1, max_length=4000)
    shot_size: str | None = Field(default=None, max_length=240)
    composition: str | None = Field(default=None, max_length=1000)
    angle_or_type: str | None = Field(default=None, max_length=400)
    movement: str | None = Field(default=None, max_length=800)
    focal_length_dof: str | None = Field(default=None, max_length=800)

    @model_validator(mode="after")
    def validate_edit(self) -> "StoryboardShotEditCommand":
        if self.reset_to_source:
            return self
        fields = (
            self.visual_description,
            self.shot_size,
            self.composition,
            self.angle_or_type,
            self.movement,
            self.focal_length_dof,
        )
        if any(value is None for value in fields):
            raise ValueError("保存分镜草稿时必须提交完整的可编辑镜头字段")
        return self
