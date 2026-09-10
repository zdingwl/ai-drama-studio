from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class SourceEvidenceResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class DialogueTextSource(StrEnum):
    ASR = "ASR"
    OCR_SUBTITLE_ADJUDICATED = "OCR_SUBTITLE_ADJUDICATED"
    USER_ASR_SELECTED = "USER_ASR_SELECTED"
    USER_OCR_SELECTED = "USER_OCR_SELECTED"
    USER_EDITED = "USER_EDITED"


class ManualDialogueChoice(StrEnum):
    ASR = "ASR"
    OCR = "OCR"
    CUSTOM = "CUSTOM"


class DialogueUtteranceRead(BaseModel):
    id: str
    utterance_number: int
    start_us: int
    end_us: int
    text: str
    language: str | None
    projected_shot_numbers: list[int]
    text_source: str = DialogueTextSource.ASR.value
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


class DialogueManualAdjudicationCommand(BaseModel):
    expected_revision: int = Field(ge=1)
    utterance_id: str = Field(min_length=1, max_length=36)
    choice: ManualDialogueChoice
    ocr_span_number: int | None = Field(default=None, ge=1)
    custom_text: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_choice_payload(self) -> "DialogueManualAdjudicationCommand":
        if self.choice == ManualDialogueChoice.OCR and self.ocr_span_number is None:
            raise ValueError("选择 OCR 时必须提供 ocr_span_number")
        if self.choice == ManualDialogueChoice.CUSTOM:
            if self.custom_text is None or not self.custom_text.strip():
                raise ValueError("自定义文本不能为空")
            self.custom_text = self.custom_text.strip()
        return self
