"""P7.1 version-safe localization source package contract.

This is a read-only handoff from current Breakdown/Final Asset truth into future
localization and remake stages. Translation/localization/final-script values must be
stored in a separate revisioned downstream model and never overwrite this source.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.app.breakdown_read_model_contract_v1 import (
    FinalCharacterDisplayV1,
    FinalPropDisplayV1,
    FinalSceneDisplayV1,
)
from engine.app.breakdown_scene_timeline_contract_v1 import (
    SceneTimelineCinematographyV1,
    SceneTimelineSceneInfoV1,
)

LOCALIZATION_SOURCE_SCHEMA_VERSION = "localization-source-v1"


class _StrictLocalizationSourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalizationSourcePersonV1(_StrictLocalizationSourceModel):
    display_name: str = Field(min_length=1)
    character: FinalCharacterDisplayV1 | None = None


class LocalizationSourcePerformanceV1(_StrictLocalizationSourceModel):
    text: str = Field(min_length=1)
    people: list[LocalizationSourcePersonV1] = Field(default_factory=list)


class LocalizationSourceDialogueV1(_StrictLocalizationSourceModel):
    """Immutable ASR-origin source dialogue."""

    source_key: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)
    speakers: list[LocalizationSourcePersonV1] = Field(default_factory=list)


class LocalizationSourceOnScreenTextV1(_StrictLocalizationSourceModel):
    """Immutable OCR-origin visible source text."""

    source_key: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)


class LocalizationSourceObservedPropV1(_StrictLocalizationSourceModel):
    """Frozen G2 visible prop observation; never Final Prop identity."""

    label: str = Field(min_length=1)
    interaction: str | None = None


class LocalizationSourceShotV1(_StrictLocalizationSourceModel):
    ordinal: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    thumbnail_url: str | None = None
    reference_url: str | None = None
    visual_description: str | None = None
    people: list[LocalizationSourcePersonV1] = Field(default_factory=list)
    performance: list[LocalizationSourcePerformanceV1] = Field(default_factory=list)
    source_dialogue: list[LocalizationSourceDialogueV1] = Field(default_factory=list)
    observed_props: list[LocalizationSourceObservedPropV1] = Field(default_factory=list)
    final_props: list[FinalPropDisplayV1] = Field(default_factory=list)
    cinematography: SceneTimelineCinematographyV1
    source_on_screen_text: list[LocalizationSourceOnScreenTextV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _source_keys_are_unique(self) -> "LocalizationSourceShotV1":
        keys = [item.source_key for item in self.source_dialogue]
        keys.extend(item.source_key for item in self.source_on_screen_text)
        if len(set(keys)) != len(keys):
            raise ValueError("同一 Shot 的 localization source_key 不允许重复")
        return self


class LocalizationSourceSceneV1(_StrictLocalizationSourceModel):
    ordinal: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    title: str = Field(min_length=1)
    story_summary: str | None = None
    scene_info: SceneTimelineSceneInfoV1
    final_scene: FinalSceneDisplayV1 | None = None
    people: list[LocalizationSourcePersonV1] = Field(default_factory=list)
    shots: list[LocalizationSourceShotV1] = Field(default_factory=list)


class LocalizationSourcePackageV1(_StrictLocalizationSourceModel):
    """Read-only P7.1 source package. No target-language copy is stored here."""

    schema_version: Literal["localization-source-v1"] = LOCALIZATION_SOURCE_SCHEMA_VERSION
    status: Literal["READY", "READY_WITH_WARNINGS"]
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    source_asset_revision_id: str | None = None
    scene_count: int = Field(ge=0)
    shot_count: int = Field(ge=0)
    source_dialogue_count: int = Field(ge=0)
    source_on_screen_text_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    scenes: list[LocalizationSourceSceneV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _aggregate_counts_match(self) -> "LocalizationSourcePackageV1":
        shots = [shot for scene in self.scenes for shot in scene.shots]
        dialogue_count = sum(len(shot.source_dialogue) for shot in shots)
        text_count = sum(len(shot.source_on_screen_text) for shot in shots)
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count 与 localization source scenes 不一致")
        if self.shot_count != len(shots):
            raise ValueError("shot_count 与 localization source shots 不一致")
        if self.source_dialogue_count != dialogue_count:
            raise ValueError("source_dialogue_count 与 source_dialogue 不一致")
        if self.source_on_screen_text_count != text_count:
            raise ValueError("source_on_screen_text_count 与 source_on_screen_text 不一致")
        scene_ordinals = [scene.ordinal for scene in self.scenes]
        shot_ordinals = [shot.ordinal for shot in shots]
        if len(set(scene_ordinals)) != len(scene_ordinals):
            raise ValueError("Localization source 不允许重复 Scene ordinal")
        if len(set(shot_ordinals)) != len(shot_ordinals):
            raise ValueError("Localization source 不允许重复 Shot ordinal")
        if self.status == "READY" and self.warnings:
            raise ValueError("READY localization source 不应携带 warnings")
        if self.status == "READY_WITH_WARNINGS" and not self.warnings:
            raise ValueError("READY_WITH_WARNINGS localization source 必须说明降级原因")
        return self


__all__ = [
    "LOCALIZATION_SOURCE_SCHEMA_VERSION",
    "LocalizationSourceDialogueV1",
    "LocalizationSourceObservedPropV1",
    "LocalizationSourceOnScreenTextV1",
    "LocalizationSourcePackageV1",
    "LocalizationSourcePerformanceV1",
    "LocalizationSourcePersonV1",
    "LocalizationSourceSceneV1",
    "LocalizationSourceShotV1",
]
