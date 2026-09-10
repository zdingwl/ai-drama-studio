from enum import StrEnum

from pydantic import BaseModel, Field


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
    shot_anchor_id: str
    shot_number: int
    start_us: int
    end_us: int
    duration_us: int
    visual_description: str
    shot_size: str
    composition: str
    angle_or_type: str
    movement: str
    focal_length_dof: str
    dialogues: list[SourceScriptDialogue] = Field(default_factory=list)


class SourceScriptScene(BaseModel):
    scene_number: int
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
