"""Independent script-first schemas; never reuse timestamped Replica P12 rows."""

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class ResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Character(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(default="", max_length=400)
    speech_style: str = Field(default="", max_length=1000)
    relations: list[str] = Field(default_factory=list)


class Scene(StrictModel):
    number: int = Field(ge=1)
    heading: str = Field(default="", max_length=400)
    summary: str = Field(min_length=1, max_length=2000)
    characters: list[str] = Field(default_factory=list)


class StoryBeat(StrictModel):
    order: int = Field(ge=1)
    function: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=2000)
    must_preserve: bool = True


class CulturalElement(StrictModel):
    source: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=80)
    story_function: str = Field(default="", max_length=1200)
    localization_risk: str = Field(default="", max_length=1200)


class AnalysisSemantic(StrictModel):
    title: str = Field(default="", max_length=300)
    synopsis: str = Field(min_length=1, max_length=8000)
    characters: list[Character] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    story_beats: list[StoryBeat] = Field(default_factory=list)
    rhythm_beats: list[StoryBeat] = Field(default_factory=list)
    cultural_elements: list[CulturalElement] = Field(default_factory=list)
    preservation_locks: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class CulturalMapping(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=400)
    target: str = Field(min_length=1, max_length=400)
    reason: str = Field(min_length=1, max_length=1500)


class PlanSemantic(StrictModel):
    creative_intent: str = Field(min_length=1, max_length=2500)
    preservation_locks: list[str] = Field(default_factory=list)
    mappings: list[CulturalMapping] = Field(default_factory=list)
    terminology: list[CulturalMapping] = Field(default_factory=list)
    dialogue_style_guide: list[str] = Field(default_factory=list)
    unresolved_decisions: list[str] = Field(default_factory=list)


class LocalizedChange(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=1000)
    target: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1500)


class LocalizedScriptSemantic(StrictModel):
    title: str = Field(default="", max_length=300)
    script_text: str = Field(min_length=1)
    changes: list[LocalizedChange] = Field(default_factory=list)
    consistency_notes: list[str] = Field(default_factory=list)


class StageRead(BaseModel):
    status: ResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    content: dict | None = None


class ScriptLocalizationStateRead(BaseModel):
    project_id: str
    analysis: StageRead
    plan: StageRead
    target_script: StageRead
    final_output: StageRead


class TargetScriptEditCommand(BaseModel):
    expected_artifact_id: str = Field(min_length=1, max_length=160)
    script_text: str = Field(min_length=1, max_length=2_000_000)
