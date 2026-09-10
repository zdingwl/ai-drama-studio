from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.shot_breakdown.schemas import SourceShotFactsContent
from app.skills.models import ArtifactType
from app.source_resolution.schemas import (
    CharacterResolutionContent,
    PropResolutionContent,
    SceneResolutionContent,
    SpeakerResolutionContent,
)
from app.understanding.schemas import SourceBibleContent


P10_SCHEMA_VERSION = "1.0"
P10_SNAPSHOT_CONTRACT = "p10-source-video-snapshot-v1"
P10_SOURCE_TRUTH_CONTRACT = "frozen-accepted-source-facts-v1"
P10_PUBLICATION_MODE = "DETERMINISTIC_FREEZE"
P10_PROFESSIONAL_SKILL_ID = "source-video-snapshot"


P10_REQUIRED_ARTIFACT_TYPES: tuple[ArtifactType, ...] = (
    ArtifactType.SOURCE_VIDEO,
    ArtifactType.SHOT_ANCHORS,
    ArtifactType.SOURCE_DIALOGUE,
    ArtifactType.SOURCE_BIBLE,
    ArtifactType.STORY_SKELETON,
    ArtifactType.RHYTHM_SKELETON,
    ArtifactType.SOURCE_SHOT_FACTS,
    ArtifactType.SOURCE_CHARACTERS,
    ArtifactType.SOURCE_SPEAKERS,
    ArtifactType.SOURCE_SCENES,
    ArtifactType.SOURCE_PROPS,
)


class SourceVideoSnapshotResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class FrozenArtifactRef(BaseModel):
    artifact_type: ArtifactType
    artifact_id: str
    revision: int = Field(ge=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotShotAnchor(BaseModel):
    shot_anchor_id: str
    shot_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    duration_us: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_time(self) -> "SnapshotShotAnchor":
        if self.end_us <= self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("snapshot shot time must preserve authoritative P5 timing")
        return self


class SnapshotDialogueUtterance(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    text: str
    language: str | None = None

    @model_validator(mode="after")
    def validate_time(self) -> "SnapshotDialogueUtterance":
        if self.end_us <= self.start_us:
            raise ValueError("snapshot dialogue end_us must be greater than start_us")
        return self


class SnapshotVisualTextSpan(BaseModel):
    span_id: str
    span_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_time(self) -> "SnapshotVisualTextSpan":
        if self.end_us <= self.start_us:
            raise ValueError("snapshot visual text end_us must be greater than start_us")
        return self


class SourceVideoSnapshotEpisode(BaseModel):
    episode_id: str
    source_asset_id: str
    episode_order: int = Field(ge=1)
    source_filename: str
    source_asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_us: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    codec_name: str
    avg_frame_rate: str
    has_audio: bool
    shot_boundary_set_id: str
    shot_boundary_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_set_id: str
    source_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    shot_anchors: list[SnapshotShotAnchor] = Field(default_factory=list)
    canonical_dialogue: list[SnapshotDialogueUtterance] = Field(default_factory=list)
    canonical_visual_text: list[SnapshotVisualTextSpan] = Field(default_factory=list)


class SourceVideoSnapshotContent(BaseModel):
    schema_version: Literal["1.0"] = P10_SCHEMA_VERSION
    title: str = "原片分析定稿"
    source_truth_contract: Literal["frozen-accepted-source-facts-v1"] = P10_SOURCE_TRUTH_CONTRACT
    frozen_artifacts: list[FrozenArtifactRef] = Field(min_length=len(P10_REQUIRED_ARTIFACT_TYPES))
    episodes: list[SourceVideoSnapshotEpisode] = Field(min_length=1)
    source_bible: SourceBibleContent
    source_shot_facts: SourceShotFactsContent
    source_characters: CharacterResolutionContent
    source_speakers: SpeakerResolutionContent
    source_scenes: SceneResolutionContent
    source_props: PropResolutionContent

    @model_validator(mode="after")
    def validate_frozen_artifact_set(self) -> "SourceVideoSnapshotContent":
        types = [item.artifact_type for item in self.frozen_artifacts]
        if len(types) != len(set(types)) or set(types) != set(P10_REQUIRED_ARTIFACT_TYPES):
            raise ValueError("snapshot frozen_artifacts must exactly cover the P10 current Source chain")
        episode_ids = [item.episode_id for item in self.episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("snapshot episode_id must be unique")
        return self


class SourceVideoSnapshotEpisodeProvenance(BaseModel):
    episode_id: str
    source_asset_id: str
    source_asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shot_boundary_set_id: str
    shot_boundary_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_set_id: str
    source_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceVideoSnapshotProvenance(BaseModel):
    snapshot_contract: Literal["p10-source-video-snapshot-v1"] = P10_SNAPSHOT_CONTRACT
    schema_version: Literal["1.0"] = P10_SCHEMA_VERSION
    source_truth_contract: Literal["frozen-accepted-source-facts-v1"] = P10_SOURCE_TRUTH_CONTRACT
    professional_skill_id: Literal["source-video-snapshot"] = P10_PROFESSIONAL_SKILL_ID
    professional_skill_version: str
    publication_mode: Literal["DETERMINISTIC_FREEZE"] = P10_PUBLICATION_MODE
    source_chain_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_artifacts: list[FrozenArtifactRef] = Field(min_length=len(P10_REQUIRED_ARTIFACT_TYPES))
    episode_inputs: list[SourceVideoSnapshotEpisodeProvenance] = Field(min_length=1)
    provider_jobs: list[dict] = Field(default_factory=list, max_length=0)
    supersedes_artifact_id: str | None = None

    @model_validator(mode="after")
    def validate_no_provider_and_artifact_set(self) -> "SourceVideoSnapshotProvenance":
        if self.provider_jobs:
            raise ValueError("P10 deterministic freeze cannot contain provider jobs")
        types = [item.artifact_type for item in self.frozen_artifacts]
        if len(types) != len(set(types)) or set(types) != set(P10_REQUIRED_ARTIFACT_TYPES):
            raise ValueError("snapshot provenance must exactly cover the P10 current Source chain")
        return self


class SourceVideoSnapshotRead(BaseModel):
    project_id: str
    status: SourceVideoSnapshotResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: SourceVideoSnapshotContent | None = None
    provenance: SourceVideoSnapshotProvenance | None = None


class SourceVideoSnapshotRevisionSummary(BaseModel):
    artifact_id: str
    revision: int
    status: SourceVideoSnapshotResultStatus
    input_fingerprint: str
    source_chain_fingerprint: str
    created_at: str
    supersedes_artifact_id: str | None = None
