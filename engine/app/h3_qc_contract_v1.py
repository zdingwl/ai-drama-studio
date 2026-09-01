"""R9 H3 quality-control and selected-output contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


GenerationQCStatus = Literal["PASS", "RETRY", "REVIEW", "WAITING_MODEL", "STALE"]
GenerationSelectionSource = Literal["AUTO", "MANUAL"]


class GenerationStructuralQCV1(_StrictModel):
    expected_duration_us: int = Field(ge=1)
    actual_duration_us: int | None = Field(default=None, ge=1)
    duration_delta_us: int | None = None
    duration_tolerance_us: int = Field(ge=1)
    duration_ok: bool
    decode_ok: bool
    has_video: bool
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fps: float | None = Field(default=None, gt=0)
    error_message: str | None = None


class GenerationSemanticQCV1(_StrictModel):
    visual_integrity: float | None = Field(default=None, ge=0, le=1)
    target_character_consistency: float | None = Field(default=None, ge=0, le=1)
    scene_consistency: float | None = Field(default=None, ge=0, le=1)
    action_camera_consistency: float | None = Field(default=None, ge=0, le=1)
    continuity_consistency: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_actor_leak: bool = False
    obvious_visual_artifact: bool = False
    reasons: list[str] = Field(default_factory=list, max_length=12)
    retry_instruction: str | None = Field(default=None, max_length=4000)
    raw: dict[str, Any] = Field(default_factory=dict)


class GenerationQualityCheckV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    generation_segment_id: str = Field(min_length=1)
    generation_attempt_id: str = Field(min_length=1)
    segment_input_fingerprint: str = Field(min_length=64, max_length=64)
    profile_version: str = Field(min_length=1, max_length=64)
    status: GenerationQCStatus
    quality_score: float | None = Field(default=None, ge=0, le=1)
    structural: GenerationStructuralQCV1
    semantic: GenerationSemanticQCV1 | None = None
    model_profile: str | None = None
    reason: str = Field(min_length=1)
    retry_instruction: str | None = Field(default=None, max_length=4000)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _pass_requires_semantic_and_structure(self) -> "GenerationQualityCheckV1":
        if self.status == "PASS":
            if not (self.structural.has_video and self.structural.decode_ok and self.structural.duration_ok):
                raise ValueError("PASS QC requires structural pass")
            if self.semantic is None:
                raise ValueError("PASS QC requires semantic result")
            if self.quality_score is None:
                raise ValueError("PASS QC requires quality_score")
        if self.status == "WAITING_MODEL" and self.semantic is not None:
            raise ValueError("WAITING_MODEL must not expose fake semantic result")
        return self


class GenerationSelectionV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    generation_segment_id: str = Field(min_length=1)
    segment_input_fingerprint: str = Field(min_length=64, max_length=64)
    selected_attempt_id: str = Field(min_length=1)
    quality_check_id: str | None = None
    selection_source: GenerationSelectionSource
    quality_score: float | None = Field(default=None, ge=0, le=1)
    created_at: str
    updated_at: str


class GenerationQualityProjectSummaryV1(_StrictModel):
    schema_version: Literal["generation-quality-summary-v1"] = "generation-quality-summary-v1"
    project_id: str = Field(min_length=1)
    check_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    waiting_model_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    checks: list[GenerationQualityCheckV1] = Field(default_factory=list)
    selections: list[GenerationSelectionV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_match(self) -> "GenerationQualityProjectSummaryV1":
        if self.check_count != len(self.checks):
            raise ValueError("check_count mismatch")
        if self.pass_count != sum(item.status == "PASS" for item in self.checks):
            raise ValueError("pass_count mismatch")
        if self.retry_count != sum(item.status == "RETRY" for item in self.checks):
            raise ValueError("retry_count mismatch")
        if self.review_count != sum(item.status == "REVIEW" for item in self.checks):
            raise ValueError("review_count mismatch")
        if self.waiting_model_count != sum(item.status == "WAITING_MODEL" for item in self.checks):
            raise ValueError("waiting_model_count mismatch")
        if self.stale_count != sum(item.status == "STALE" for item in self.checks):
            raise ValueError("stale_count mismatch")
        if self.selected_count != len(self.selections):
            raise ValueError("selected_count mismatch")
        return self


__all__ = [
    "GenerationQCStatus",
    "GenerationQualityCheckV1",
    "GenerationQualityProjectSummaryV1",
    "GenerationSelectionSource",
    "GenerationSelectionV1",
    "GenerationSemanticQCV1",
    "GenerationStructuralQCV1",
]
