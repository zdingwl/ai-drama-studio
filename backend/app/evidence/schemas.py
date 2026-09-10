from enum import StrEnum

from pydantic import BaseModel, Field


class SourceEvidenceResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class DialogueUtteranceRead(BaseModel):
    id: str
    utterance_number: int
    start_us: int
    end_us: int
    text: str
    language: str | None
    projected_shot_numbers: list[int]
    text_source: str = "ASR"
    asr_text: str | None = None
    ocr_text: str | None = None
    ocr_span_numbers: list[int] = Field(default_factory=list)
    adjudication_policy: str | None = None
    adjudication_reason: str | None = None


class VisualTextSpanRead(BaseModel):
    id: str
    span_number: int
    start_us: int
    end_us: int
    text: str
    confidence: float | None


class EpisodeSourceEvidenceRead(BaseModel):
    episode_id: str
    episode_order: int
    source_filename: str
    status: SourceEvidenceResultStatus
    revision: int | None
    artifact_revision: int | None
    dialogue_count: int
    visual_text_count: int
    raw_asr_segment_count: int
    raw_ocr_observation_count: int
    dialogue: list[DialogueUtteranceRead]
    visual_text: list[VisualTextSpanRead]
