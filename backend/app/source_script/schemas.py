from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.understanding.schemas import RhythmSkeleton, StorySkeleton, TimeRange


SOURCE_SCRIPT_SCHEMA_VERSION = "1.0"
SOURCE_SCRIPT_CONTRACT = "script-first-source-v1"
SOURCE_SCRIPT_PUBLICATION_MODE = "DETERMINISTIC_P6_P7_PROJECTION"


class SourceScriptResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class SourceScriptDialogueLine(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    text: str
    language: str | None = None
    source_character_id: str | None = None
    speaker_name: str = "说话人待确认"

    @model_validator(mode="after")
    def validate_time(self) -> "SourceScriptDialogueLine":
        if self.end_us <= self.start_us:
            raise ValueError("source script dialogue end_us must be greater than start_us")
        return self


class SourceScriptStorySegment(BaseModel):
    segment_number: int = Field(ge=1)
    time_range: TimeRange
    visual_description: str
    story_summary: str
    narrative_function: str
    dialogue_utterance_ids: list[str] = Field(default_factory=list)


class SourceScriptCharacter(BaseModel):
    source_character_id: str
    name: str
    story_function: str
    appearance_baseline: str


class SourceScriptSceneIdentity(BaseModel):
    source_scene_id: str
    name: str
    time_ranges: list[TimeRange] = Field(default_factory=list)
    spatial_relationship: str
    environment_details: str


class SourceScriptProp(BaseModel):
    source_prop_id: str
    name: str
    time_ranges: list[TimeRange] = Field(default_factory=list)
    appearance_state: str
    story_function: str | None = None


class SourceScriptEpisode(BaseModel):
    episode_id: str
    episode_order: int = Field(ge=1)
    source_filename: str
    duration_us: int = Field(gt=0)
    story_summary: str
    story_background: str
    narrative_structure: str
    dialogue: list[SourceScriptDialogueLine] = Field(default_factory=list)
    story_segments: list[SourceScriptStorySegment] = Field(default_factory=list)
    characters: list[SourceScriptCharacter] = Field(default_factory=list)
    scenes: list[SourceScriptSceneIdentity] = Field(default_factory=list)
    props: list[SourceScriptProp] = Field(default_factory=list)
    story_skeleton: StorySkeleton
    rhythm_skeleton: RhythmSkeleton


class SourceScriptContent(BaseModel):
    schema_version: Literal["1.0"] = SOURCE_SCRIPT_SCHEMA_VERSION
    source_truth_contract: Literal["script-first-source-v1"] = SOURCE_SCRIPT_CONTRACT
    title: str = "原片剧本"
    episodes: list[SourceScriptEpisode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_episode_ids(self) -> "SourceScriptContent":
        ids = [item.episode_id for item in self.episodes]
        if len(ids) != len(set(ids)):
            raise ValueError("source script episode_id must be unique")
        return self


class SourceScriptProvenance(BaseModel):
    schema_version: Literal["1.0"] = SOURCE_SCRIPT_SCHEMA_VERSION
    contract: Literal["script-first-source-v1"] = SOURCE_SCRIPT_CONTRACT
    publication_mode: Literal["DETERMINISTIC_P6_P7_PROJECTION"] = SOURCE_SCRIPT_PUBLICATION_MODE
    source_video_artifact_id: str
    source_video_revision: int = Field(ge=1)
    source_video_fingerprint: str
    source_dialogue_artifact_id: str
    source_dialogue_revision: int = Field(ge=1)
    source_dialogue_fingerprint: str
    source_bible_artifact_id: str
    source_bible_revision: int = Field(ge=1)
    source_bible_fingerprint: str
    generated_by_task_id: str | None = None
    supersedes_artifact_id: str | None = None
    provider_jobs: list[dict] = Field(default_factory=list, max_length=0)


class SourceScriptArtifactRead(BaseModel):
    project_id: str
    status: SourceScriptResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: SourceScriptContent | None = None
    provenance: SourceScriptProvenance | None = None
