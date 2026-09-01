"""P7.2 revisioned Localization Draft contract.

The write surface owns only target-side copy and review decisions. Source text is read
from the immutable P7.1 snapshot and is never accepted from edit requests.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.app.localization_source_contract_v1 import LocalizationSourcePersonV1


LOCALIZATION_DRAFT_SCHEMA_VERSION = "localization-draft-v1"
LocalizationDraftStatus = Literal["DRAFT", "IN_REVIEW", "FINAL"]
LocalizationDraftDecision = Literal["PENDING", "LOCALIZE", "KEEP_SOURCE", "OMIT"]
LocalizationDraftEntryKind = Literal["dialogue", "on_screen_text"]


class _StrictLocalizationDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalizationDraftEditV1(_StrictLocalizationDraftModel):
    """Target-side state for one immutable P7 source_key.

    No source_text field exists by design, so API writes cannot overwrite ASR/OCR truth.
    DRAFT may save partial translated/localized/final layers; review readiness is checked
    by the revision workflow rather than this per-entry transport model.
    """

    source_key: str = Field(min_length=1)
    decision: LocalizationDraftDecision = "PENDING"
    translated_text: str | None = None
    localized_text: str | None = None
    final_text: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _validate_decision(self) -> "LocalizationDraftEditV1":
        if self.decision in {"KEEP_SOURCE", "OMIT"} and self.final_text not in {None, ""}:
            raise ValueError("KEEP_SOURCE / OMIT 不应写入 final_text")
        return self


class LocalizationDraftEntryV1(_StrictLocalizationDraftModel):
    source_key: str = Field(min_length=1)
    kind: LocalizationDraftEntryKind
    scene_ordinal: int = Field(ge=1)
    shot_ordinal: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)
    speakers: list[LocalizationSourcePersonV1] = Field(default_factory=list)
    decision: LocalizationDraftDecision
    translated_text: str | None = None
    localized_text: str | None = None
    final_text: str | None = None
    effective_final_text: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _validate_effective_text(self) -> "LocalizationDraftEntryV1":
        if self.end_us < self.start_us:
            raise ValueError("Localization entry 时间范围非法")
        if self.decision == "LOCALIZE":
            expected = (self.final_text or "").strip() or None
            if self.effective_final_text != expected:
                raise ValueError("LOCALIZE effective_final_text 必须与 final_text 一致")
        elif self.decision == "KEEP_SOURCE":
            if self.final_text not in {None, ""} or self.effective_final_text != self.source_text:
                raise ValueError("KEEP_SOURCE 必须直接使用 source_text")
        elif self.decision == "OMIT":
            if self.final_text not in {None, ""} or self.effective_final_text is not None:
                raise ValueError("OMIT 不应产生 final text")
        elif self.effective_final_text is not None:
            raise ValueError("PENDING 不应产生 effective_final_text")
        return self


class LocalizationDraftShotV1(_StrictLocalizationDraftModel):
    ordinal: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    reference_url: str | None = None
    thumbnail_url: str | None = None
    visual_description: str | None = None
    people: list[LocalizationSourcePersonV1] = Field(default_factory=list)
    entries: list[LocalizationDraftEntryV1] = Field(default_factory=list)


class LocalizationDraftSceneV1(_StrictLocalizationDraftModel):
    ordinal: int = Field(ge=1)
    title: str = Field(min_length=1)
    story_summary: str | None = None
    shots: list[LocalizationDraftShotV1] = Field(default_factory=list)


class LocalizationDraftProgressV1(_StrictLocalizationDraftModel):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    localized: int = Field(ge=0)
    keep_source: int = Field(ge=0)
    omitted: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_match(self) -> "LocalizationDraftProgressV1":
        if self.total != self.pending + self.localized + self.keep_source + self.omitted:
            raise ValueError("Localization progress 计数不一致")
        return self


class LocalizationDraftViewV1(_StrictLocalizationDraftModel):
    schema_version: Literal["localization-draft-v1"] = LOCALIZATION_DRAFT_SCHEMA_VERSION
    revision_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    kind: str = Field(min_length=1)
    status: LocalizationDraftStatus
    is_current: bool
    stale: bool
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    source_schema_version: str = Field(min_length=1)
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    source_asset_revision_id: str | None = None
    source_fingerprint: str = Field(min_length=64, max_length=64)
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    progress: LocalizationDraftProgressV1
    scenes: list[LocalizationDraftSceneV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: str = Field(min_length=1)


class LocalizationRevisionSummaryV1(_StrictLocalizationDraftModel):
    id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    kind: str = Field(min_length=1)
    status: LocalizationDraftStatus
    is_current: bool
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    source_asset_revision_id: str | None = None
    source_fingerprint: str = Field(min_length=64, max_length=64)
    note: str | None = None
    created_at: str = Field(min_length=1)


__all__ = [
    "LOCALIZATION_DRAFT_SCHEMA_VERSION",
    "LocalizationDraftDecision",
    "LocalizationDraftEditV1",
    "LocalizationDraftEntryKind",
    "LocalizationDraftEntryV1",
    "LocalizationDraftProgressV1",
    "LocalizationDraftSceneV1",
    "LocalizationDraftShotV1",
    "LocalizationDraftStatus",
    "LocalizationDraftViewV1",
    "LocalizationRevisionSummaryV1",
]
