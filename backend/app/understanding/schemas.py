from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


NonEmptyText = Annotated[str, Field(min_length=1, max_length=12000)]
ShortText = Annotated[str, Field(min_length=1, max_length=1000)]


class SourceBibleResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class TimeRange(BaseModel):
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "TimeRange":
        if self.end_us <= self.start_us:
            raise ValueError("end_us must be greater than start_us")
        return self


class ClaimSupportLevel(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


class ClaimGrounding(BaseModel):
    support_level: ClaimSupportLevel = ClaimSupportLevel.UNKNOWN
    dialogue_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    visual_text_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    video_time_ranges: list[TimeRange] = Field(default_factory=list, max_length=40)
    note: ShortText | None = None

    @model_validator(mode="after")
    def validate_support_contract(self) -> "ClaimGrounding":
        has_support = bool(self.dialogue_evidence_ids or self.visual_text_evidence_ids or self.video_time_ranges)
        if self.support_level in {ClaimSupportLevel.FACT, ClaimSupportLevel.INFERENCE} and not has_support:
            raise ValueError(f"{self.support_level.value} 必须至少提供 Evidence ID 或完整 Episode 视频时间依据")
        if self.support_level == ClaimSupportLevel.UNKNOWN and has_support:
            raise ValueError("UNKNOWN 不得携带 Evidence ID 或视频时间依据；若已有支持应标为 FACT 或 INFERENCE")
        return self


class MaterialBaseline(BaseModel):
    episode_id: str
    episode_order: int = Field(ge=1)
    source_filename: str
    media_duration_us: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect_ratio: str
    avg_frame_rate: str
    codec_name: str
    has_audio: bool
    effective_content_range: TimeRange | None = None
    visual_format_notes: list[ShortText] = Field(default_factory=list, max_length=20)


class OverallAnalysis(BaseModel):
    story_summary: NonEmptyText
    story_background: NonEmptyText
    story_background_grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)
    genre: list[ShortText] = Field(default_factory=list, max_length=12)
    # Backward-compatible field name. In the grounded P7 contract this may only contain
    # source-internal rules/facts, never social generalizations or legal conclusions.
    world_rules: list[ShortText] = Field(default_factory=list, max_length=30)
    world_rule_groundings: list[ClaimGrounding] = Field(default_factory=list, max_length=30)
    narrative_structure: NonEmptyText
    audiovisual_style: NonEmptyText
    rhythm_overview: NonEmptyText


class TimedStorySegment(BaseModel):
    segment_number: int = Field(ge=1)
    time_range: TimeRange
    visual_description: NonEmptyText
    story_summary: NonEmptyText
    narrative_function: ShortText
    dialogue_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    visual_text_evidence_ids: list[str] = Field(default_factory=list, max_length=80)


class CharacterState(BaseModel):
    time_range: TimeRange
    state: ShortText


class CharacterProfile(BaseModel):
    character_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    identity_grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)
    story_function: NonEmptyText
    appearance_baseline: NonEmptyText
    states: list[CharacterState] = Field(default_factory=list, max_length=40)


class CharacterRelationship(BaseModel):
    source_character_id: str = Field(min_length=1, max_length=80)
    target_character_id: str = Field(min_length=1, max_length=80)
    relationship: NonEmptyText
    grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)
    change_summary: NonEmptyText | None = None


class SceneProfile(BaseModel):
    scene_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    time_ranges: list[TimeRange] = Field(default_factory=list, max_length=40)
    spatial_relationship: NonEmptyText
    environment_details: NonEmptyText
    grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)


class PropProfile(BaseModel):
    prop_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    time_ranges: list[TimeRange] = Field(default_factory=list, max_length=40)
    appearance_state: NonEmptyText
    appearance_grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)
    story_function: NonEmptyText | None = None
    story_function_grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)


class StoryEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=80)
    time_range: TimeRange
    summary: NonEmptyText
    participants: list[str] = Field(default_factory=list, max_length=40)
    consequences: NonEmptyText
    grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)


class EmotionBeat(BaseModel):
    time_range: TimeRange
    subject: str = Field(min_length=1, max_length=160)
    emotion: ShortText
    change: NonEmptyText


class StoryBeatType(StrEnum):
    HOOK = "HOOK"
    CONFLICT = "CONFLICT"
    ESCALATION = "ESCALATION"
    REVEAL = "REVEAL"
    REVERSAL = "REVERSAL"
    EMOTIONAL_PEAK = "EMOTIONAL_PEAK"
    PAYOFF = "PAYOFF"
    CLIFFHANGER = "CLIFFHANGER"
    RELATIONSHIP_CHANGE = "RELATIONSHIP_CHANGE"


class StoryBeat(BaseModel):
    beat_type: StoryBeatType
    time_range: TimeRange
    summary: NonEmptyText
    importance: int = Field(ge=1, le=5)


class StorySkeleton(BaseModel):
    premise: NonEmptyText
    central_conflict: NonEmptyText
    beats: list[StoryBeat] = Field(min_length=1, max_length=40)


class RhythmPhase(BaseModel):
    time_range: TimeRange
    pace: str = Field(min_length=1, max_length=80)
    scene_rhythm: NonEmptyText
    dialogue_reaction_rhythm: NonEmptyText
    cut_timing_notes: NonEmptyText
    key_beat_refs: list[str] = Field(default_factory=list, max_length=30)
    allowable_deviation_ms: int = Field(ge=0, le=10000)


class RhythmSkeleton(BaseModel):
    overall_pace: NonEmptyText
    phases: list[RhythmPhase] = Field(min_length=1, max_length=40)


class EpisodeUnderstandingSemantic(BaseModel):
    effective_content_range: TimeRange | None = None
    visual_format_notes: list[ShortText] = Field(default_factory=list, max_length=20)
    overall_analysis: OverallAnalysis
    timed_script: list[TimedStorySegment] = Field(min_length=1, max_length=500)
    characters: list[CharacterProfile] = Field(default_factory=list, max_length=80)
    relationships: list[CharacterRelationship] = Field(default_factory=list, max_length=160)
    scenes: list[SceneProfile] = Field(default_factory=list, max_length=120)
    key_props: list[PropProfile] = Field(default_factory=list, max_length=120)
    story_events: list[StoryEvent] = Field(default_factory=list, max_length=160)
    emotion_timeline: list[EmotionBeat] = Field(default_factory=list, max_length=160)
    story_skeleton: StorySkeleton
    rhythm_skeleton: RhythmSkeleton


class SourceBibleEpisode(BaseModel):
    material_baseline: MaterialBaseline
    overall_analysis: OverallAnalysis
    timed_script: list[TimedStorySegment]
    characters: list[CharacterProfile]
    relationships: list[CharacterRelationship]
    scenes: list[SceneProfile]
    key_props: list[PropProfile]
    story_events: list[StoryEvent]
    emotion_timeline: list[EmotionBeat]
    story_skeleton: StorySkeleton
    rhythm_skeleton: RhythmSkeleton


class SourceBibleContent(BaseModel):
    schema_version: str = "1.1"
    title: str = "源作概览分析"
    episodes: list[SourceBibleEpisode] = Field(min_length=1)


class EpisodeEvidenceProvenance(BaseModel):
    episode_id: str
    source_evidence_set_id: str
    evidence_fingerprint: str


class ProviderJobProvenance(BaseModel):
    provider_job_id: str
    episode_id: str
    provider: str
    model: str
    payload_fingerprint: str
    remote_job_id: str | None = None


class SourceBibleProvenance(BaseModel):
    source_video_artifact_id: str
    source_video_fingerprint: str
    source_dialogue_artifact_id: str
    source_dialogue_fingerprint: str
    shot_anchors_artifact_id: str | None = None
    shot_anchors_fingerprint: str | None = None
    episode_evidence_sets: list[EpisodeEvidenceProvenance]
    provider_jobs: list[ProviderJobProvenance] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    schema_version: str
    professional_skill_id: str | None = None
    professional_skill_version: str | None = None
    grounding_contract: str | None = None
    generated_by_task_id: str | None = None
    edit_parent_artifact_id: str | None = None


class SourceBibleRead(BaseModel):
    project_id: str
    status: SourceBibleResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: SourceBibleContent | None = None
    provenance: SourceBibleProvenance | None = None
    story_skeleton_artifact_id: str | None = None
    rhythm_skeleton_artifact_id: str | None = None


class SourceBibleRevisionSummary(BaseModel):
    artifact_id: str
    revision: int
    status: SourceBibleResultStatus
    input_fingerprint: str
    created_at: str
    edit_parent_artifact_id: str | None = None


class SourceBibleEditCommand(BaseModel):
    content: SourceBibleContent