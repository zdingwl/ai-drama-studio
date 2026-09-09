from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ShotBreakdownResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class DialogueDelivery(StrEnum):
    DIALOGUE = "DIALOGUE"
    VOICEOVER = "VOICEOVER"
    OFFSCREEN = "OFFSCREEN"
    UNKNOWN = "UNKNOWN"


class CameraLanguage(BaseModel):
    shot_size: str = Field(min_length=1, max_length=120)
    composition: str = Field(min_length=1, max_length=300)
    angle_or_type: str = Field(min_length=1, max_length=160)
    movement: str = Field(min_length=1, max_length=240)
    focal_length_dof: str = Field(min_length=1, max_length=240)


class ShotSubjectBindingsSemantic(BaseModel):
    character_ids: list[str] = Field(default_factory=list)
    scene_ids: list[str] = Field(default_factory=list)
    prop_ids: list[str] = Field(default_factory=list)
    unresolved_subject_notes: list[str] = Field(default_factory=list)


class ShotDialogueAnnotationSemantic(BaseModel):
    utterance_number: int = Field(ge=1)
    delivery: DialogueDelivery = DialogueDelivery.UNKNOWN


class SourceShotSemantic(BaseModel):
    shot_number: int = Field(ge=1)
    visual_description: str = Field(min_length=1, max_length=1200)
    camera_language: CameraLanguage
    bindings: ShotSubjectBindingsSemantic = Field(default_factory=ShotSubjectBindingsSemantic)
    dialogue_annotations: list[ShotDialogueAnnotationSemantic] = Field(default_factory=list)
    sound_effects: list[str] = Field(default_factory=list)
    ambience: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_dialogue_annotations(self) -> "SourceShotSemantic":
        numbers = [item.utterance_number for item in self.dialogue_annotations]
        if len(numbers) != len(set(numbers)):
            raise ValueError("dialogue_annotations utterance_number must be unique per shot")
        return self


class EpisodeShotBreakdownSemantic(BaseModel):
    shots: list[SourceShotSemantic] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_shot_numbers(self) -> "EpisodeShotBreakdownSemantic":
        numbers = [item.shot_number for item in self.shots]
        if len(numbers) != len(set(numbers)):
            raise ValueError("shot_number must be unique")
        return self


class BoundSubjectRef(BaseModel):
    id: str
    label: str


class CanonicalDialogueBinding(BaseModel):
    utterance_id: str
    utterance_number: int = Field(ge=1)
    utterance_start_us: int = Field(ge=0)
    utterance_end_us: int = Field(gt=0)
    overlap_start_us: int = Field(ge=0)
    overlap_end_us: int = Field(gt=0)
    text: str
    language: str | None = None
    delivery: DialogueDelivery = DialogueDelivery.UNKNOWN

    @model_validator(mode="after")
    def valid_overlap(self) -> "CanonicalDialogueBinding":
        if self.utterance_end_us <= self.utterance_start_us:
            raise ValueError("utterance time range is invalid")
        if self.overlap_end_us <= self.overlap_start_us:
            raise ValueError("dialogue overlap must be positive")
        if self.overlap_start_us < self.utterance_start_us or self.overlap_end_us > self.utterance_end_us:
            raise ValueError("dialogue overlap must stay inside canonical utterance")
        return self


class SourceShotBindings(BaseModel):
    characters: list[BoundSubjectRef] = Field(default_factory=list)
    scenes: list[BoundSubjectRef] = Field(default_factory=list)
    props: list[BoundSubjectRef] = Field(default_factory=list)
    unresolved_subject_notes: list[str] = Field(default_factory=list)


class SourceShotFact(BaseModel):
    shot_anchor_id: str
    shot_number: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    duration_us: int = Field(gt=0)
    visual_description: str
    camera_language: CameraLanguage
    bindings: SourceShotBindings
    dialogue: list[CanonicalDialogueBinding] = Field(default_factory=list)
    sound_effects: list[str] = Field(default_factory=list)
    ambience: list[str] = Field(default_factory=list)
    visual_text_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_anchor_range(self) -> "SourceShotFact":
        if self.end_us <= self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("shot time range must exactly match the authoritative anchor")
        return self


class SourceShotFactsEpisode(BaseModel):
    episode_id: str
    episode_order: int = Field(ge=1)
    source_filename: str
    shots: list[SourceShotFact] = Field(default_factory=list)


class SourceShotFactsContent(BaseModel):
    schema_version: str = "1.0"
    title: str = "逐镜精细拉片"
    episodes: list[SourceShotFactsEpisode] = Field(default_factory=list)


class ShotBreakdownProvenance(BaseModel):
    source_video_artifact_id: str
    source_video_fingerprint: str
    source_bible_artifact_id: str
    source_bible_fingerprint: str
    shot_anchors_artifact_id: str
    shot_anchors_fingerprint: str
    source_dialogue_artifact_id: str
    source_dialogue_fingerprint: str
    episode_evidence_sets: list[dict] = Field(default_factory=list)
    provider_jobs: list[dict] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    schema_version: str
    professional_skill_id: str
    professional_skill_version: str | None = None
    source_truth_contract: str
    generated_by_task_id: str | None = None
    supersedes_artifact_id: str | None = None


class ShotBreakdownRead(BaseModel):
    project_id: str
    status: ShotBreakdownResultStatus
    artifact_id: str | None = None
    revision: int | None = None
    input_fingerprint: str | None = None
    content: SourceShotFactsContent | None = None
    provenance: ShotBreakdownProvenance | None = None


class ShotBreakdownRevisionSummary(BaseModel):
    artifact_id: str
    revision: int
    status: ShotBreakdownResultStatus
    input_fingerprint: str
    created_at: str
    supersedes_artifact_id: str | None = None
