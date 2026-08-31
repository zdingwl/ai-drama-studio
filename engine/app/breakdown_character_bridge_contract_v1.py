"""P5 Breakdown ↔ Character 安全桥的只读输出 Contract。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


BREAKDOWN_CHARACTER_BRIDGE_SCHEMA_VERSION = "breakdown-character-bridge-v1"
BREAKDOWN_CHARACTER_BRIDGE_PROFILE = "breakdown-character-presence-signature-p5-v1"


class _StrictBridgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BreakdownCharacterPersonResolutionV1(_StrictBridgeModel):
    scene_person_ref: str = Field(pattern=r"^P[1-9][0-9]*$")
    local_subject_id: str = Field(min_length=1)
    local_subject_ordinal: int = Field(ge=1)
    local_display_name: str = Field(min_length=1)
    status: Literal["RESOLVED", "UNRESOLVED"]
    character_id: str | None = None
    character_name: str | None = None
    support_shot_ids: list[str] = Field(default_factory=list)
    support_shot_ordinals: list[int] = Field(default_factory=list)
    resolution_basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_resolution_shape(self) -> "BreakdownCharacterPersonResolutionV1":
        if self.status == "RESOLVED":
            if not self.character_id or not self.character_name:
                raise ValueError("RESOLVED 人物必须包含 Character id/name")
        elif self.character_id is not None or self.character_name is not None:
            raise ValueError("UNRESOLVED 人物不得携带 Character id/name")
        if len(self.support_shot_ids) != len(self.support_shot_ordinals):
            raise ValueError("support Shot id/ordinal 数量必须一致")
        return self


class BreakdownCharacterSceneResolutionV1(_StrictBridgeModel):
    scene_segment_id: str = Field(min_length=1)
    scene_ordinal: int = Field(ge=1)
    subject_aware_shot_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    people: list[BreakdownCharacterPersonResolutionV1] = Field(default_factory=list)


class BreakdownCharacterResolutionPayloadV1(_StrictBridgeModel):
    schema_version: Literal["breakdown-character-bridge-v1"] = BREAKDOWN_CHARACTER_BRIDGE_SCHEMA_VERSION
    profile: Literal["breakdown-character-presence-signature-p5-v1"] = BREAKDOWN_CHARACTER_BRIDGE_PROFILE
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    breakdown_run_id: str = Field(min_length=1)
    shot_revision_id: str = Field(min_length=1)
    asset_revision_id: str | None = None
    scene_count: int = Field(ge=0)
    person_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    scenes: list[BreakdownCharacterSceneResolutionV1] = Field(default_factory=list)


__all__ = [
    "BREAKDOWN_CHARACTER_BRIDGE_PROFILE",
    "BREAKDOWN_CHARACTER_BRIDGE_SCHEMA_VERSION",
    "BreakdownCharacterPersonResolutionV1",
    "BreakdownCharacterResolutionPayloadV1",
    "BreakdownCharacterSceneResolutionV1",
]
