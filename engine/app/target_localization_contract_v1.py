"""Target-side character/scene localization contract for the remake pipeline.

This layer is downstream of SourceDramaSnapshot. It never rewrites source Character,
Scene, Shot, ASR or OCR truth. Every row stays anchored to the current source fingerprint
and current project scene policy.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictTargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


TargetStatus = Literal["READY", "REVIEW"]
SceneDecision = Literal["KEEP", "LOCALIZE", "REVIEW"]
DecisionSource = Literal["PROJECT_POLICY", "AI", "MANUAL"]


class TargetCharacterV1(_StrictTargetModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    source_character_id: str = Field(min_length=1)
    source_character_name: str = Field(min_length=1)
    source_character_signature: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    appearance_profile: str = Field(min_length=1)
    generation_prompt: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: TargetStatus
    decision_source: DecisionSource
    reference_assets: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class SceneLocalizationMappingV1(_StrictTargetModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    scene_key: str = Field(min_length=1)
    source_scene_id: str | None = None
    source_scene_name: str | None = None
    source_scene_signature: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    project_policy: Literal["AUTO", "KEEP", "LOCALIZE"]
    decision: SceneDecision
    decision_source: DecisionSource
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    target_label: str | None = None
    target_description: str | None = None
    reason: str | None = None
    status: TargetStatus
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _valid_decision(self) -> "SceneLocalizationMappingV1":
        if self.decision == "LOCALIZE" and not self.target_description:
            raise ValueError("LOCALIZE scene must provide target_description")
        if self.status == "READY" and self.decision == "REVIEW":
            raise ValueError("READY scene mapping cannot use REVIEW decision")
        return self


class TargetLocalizationBundleV1(_StrictTargetModel):
    schema_version: Literal["target-localization-v1"] = "target-localization-v1"
    project_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    target_language: str = Field(min_length=1)
    target_region: str = Field(min_length=1)
    scene_policy: Literal["AUTO", "KEEP", "LOCALIZE"]
    status: TargetStatus
    target_character_count: int = Field(ge=0)
    scene_mapping_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    target_characters: list[TargetCharacterV1] = Field(default_factory=list)
    scene_mappings: list[SceneLocalizationMappingV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_bundle(self) -> "TargetLocalizationBundleV1":
        if self.target_character_count != len(self.target_characters):
            raise ValueError("target_character_count mismatch")
        if self.scene_mapping_count != len(self.scene_mappings):
            raise ValueError("scene_mapping_count mismatch")
        reviews = sum(item.status == "REVIEW" for item in self.target_characters)
        reviews += sum(item.status == "REVIEW" for item in self.scene_mappings)
        if reviews != self.review_count:
            raise ValueError("review_count mismatch")
        if self.status == "READY" and reviews:
            raise ValueError("READY bundle cannot contain review items")
        if any(item.project_id != self.project_id for item in self.target_characters):
            raise ValueError("TargetCharacter belongs to another project")
        if any(item.project_id != self.project_id for item in self.scene_mappings):
            raise ValueError("SceneLocalizationMapping belongs to another project")
        if any(item.source_fingerprint != self.source_fingerprint for item in self.target_characters):
            raise ValueError("TargetCharacter source fingerprint is stale")
        if any(item.source_fingerprint != self.source_fingerprint for item in self.scene_mappings):
            raise ValueError("SceneLocalizationMapping source fingerprint is stale")
        if any(item.project_policy != self.scene_policy for item in self.scene_mappings):
            raise ValueError("SceneLocalizationMapping project policy is stale")
        if any(item.target_language != self.target_language or item.target_region != self.target_region for item in self.target_characters):
            raise ValueError("TargetCharacter locale is stale")
        return self


__all__ = [
    "SceneLocalizationMappingV1",
    "TargetCharacterV1",
    "TargetLocalizationBundleV1",
]
