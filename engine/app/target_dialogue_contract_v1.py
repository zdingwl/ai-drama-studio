"""Target dialogue + target voice contract for localized remake R5."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetVoiceProfileV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    target_character_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_character_signature: str = Field(min_length=64, max_length=64)
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    runtime_profile: Literal["QWEN3_TTS_VOICE_DESIGN_CLONE_V1"]
    voice_design_prompt: str = Field(min_length=1)
    reference_text: str = Field(min_length=1)
    reference_audio_path: str | None = None
    voice_fingerprint: str = Field(min_length=64, max_length=64)
    status: Literal["PLANNED", "REFERENCE_READY", "FAILED"]
    error_message: str | None = None
    created_at: str
    updated_at: str


class TargetDialogueV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    shot_key: str = Field(min_length=1)
    source_dialogue_key: str = Field(min_length=1)
    source_dialogue_signature: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    source_start_us: int = Field(ge=0)
    source_end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)
    source_character_id: str | None = None
    target_character_id: str | None = None
    target_voice_profile_id: str | None = None
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    translated_text: str | None = None
    localized_text: str | None = None
    final_text: str | None = None
    translation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    decision_source: Literal["AI", "MANUAL"]
    status: Literal["READY", "REVIEW"]
    audio_status: Literal["PENDING", "READY", "NOT_CONFIGURED", "UNSUPPORTED_LANGUAGE", "FAILED"]
    audio_path: str | None = None
    speech_duration_us: int | None = Field(default=None, ge=1)
    tts_runtime_profile: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _validate_ready(self) -> "TargetDialogueV1":
        if self.source_end_us < self.source_start_us:
            raise ValueError("source dialogue time range is invalid")
        if self.status == "READY":
            if not self.target_character_id:
                raise ValueError("READY TargetDialogue needs target_character_id")
            if not self.final_text:
                raise ValueError("READY TargetDialogue needs final_text")
        if self.audio_status == "READY":
            if not self.audio_path or not self.speech_duration_us or not self.target_voice_profile_id:
                raise ValueError("READY dialogue audio needs path/duration/voice")
        return self


class TargetDialogueBundleV1(_StrictModel):
    schema_version: Literal["target-dialogue-v1"] = "target-dialogue-v1"
    project_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    status: Literal["READY", "REVIEW", "TEXT_READY_AUDIO_PENDING"]
    voice_profile_count: int = Field(ge=0)
    dialogue_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    audio_ready_count: int = Field(ge=0)
    voice_profiles: list[TargetVoiceProfileV1] = Field(default_factory=list)
    dialogues: list[TargetDialogueV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_bundle(self) -> "TargetDialogueBundleV1":
        if self.voice_profile_count != len(self.voice_profiles):
            raise ValueError("voice_profile_count mismatch")
        if self.dialogue_count != len(self.dialogues):
            raise ValueError("dialogue_count mismatch")
        reviews = sum(item.status == "REVIEW" for item in self.dialogues)
        if self.review_count != reviews:
            raise ValueError("review_count mismatch")
        if self.audio_ready_count != sum(item.audio_status == "READY" for item in self.dialogues):
            raise ValueError("audio_ready_count mismatch")
        if any(item.project_id != self.project_id for item in self.voice_profiles + self.dialogues):
            raise ValueError("target dialogue bundle contains another project")
        if any(item.source_fingerprint != self.source_fingerprint for item in self.voice_profiles + self.dialogues):
            raise ValueError("target dialogue bundle contains stale source fingerprint")
        if any(item.target_language != self.target_language or item.target_region != self.target_region for item in self.voice_profiles + self.dialogues):
            raise ValueError("target dialogue bundle locale mismatch")
        if self.status == "READY" and (reviews or self.audio_ready_count != self.dialogue_count):
            raise ValueError("READY target dialogue bundle must have all text and audio ready")
        if self.status == "REVIEW" and reviews == 0:
            raise ValueError("REVIEW target dialogue bundle needs review items")
        return self


__all__ = ["TargetDialogueBundleV1", "TargetDialogueV1", "TargetVoiceProfileV1"]
