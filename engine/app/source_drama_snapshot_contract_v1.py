"""Stable source-drama read contract for the localized-remake pipeline.

This contract is intentionally product-oriented. It hides the historical G2/P5/P6/P7
implementation names and exposes only source facts needed by TargetCharacter, scene
localization, dialogue timing and MiniMax H3 generation.

The snapshot is read-only source truth. Target-language text, target characters, target
scenes, TTS, timing decisions and generation outputs must live in downstream models.

Dialogue has two deliberately different levels:
- ``SourceDramaDialogueUtteranceV1`` is the complete source utterance business object.
- ``SourceDramaDialogueV1`` is that utterance's projection inside one source Shot.

One utterance may therefore project to multiple Shots. Downstream translation/TTS must
consume utterances, while timing/reference-video logic may consume the projections.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.app.breakdown_scene_timeline_contract_v1 import (
    SceneTimelineCinematographyV1,
    SceneTimelineSceneInfoV1,
)


SOURCE_DRAMA_SNAPSHOT_SCHEMA_VERSION = "source-drama-snapshot-v1"
SOURCE_DRAMA_PROJECT_SCHEMA_VERSION = "source-drama-project-snapshot-v1"


class _StrictSourceDramaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceDramaAssetRefV1(_StrictSourceDramaModel):
    """Stable current Final Asset display reference used by downstream remake models."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cover_url: str | None = None


class SourceDramaPersonV1(_StrictSourceDramaModel):
    """One scene-local source person, optionally resolved to a project Character."""

    person_key: str = Field(min_length=1)
    scene_person_ref: str = Field(pattern=r"^P[1-9][0-9]*$")
    display_name: str = Field(min_length=1)
    appearance: str | None = None
    character: SourceDramaAssetRefV1 | None = None


class SourceDramaPerformanceV1(_StrictSourceDramaModel):
    text: str = Field(min_length=1)
    people: list[str] = Field(default_factory=list, description="person_key references")


class SourceDramaDialogueV1(_StrictSourceDramaModel):
    """One complete utterance projected onto one source Shot."""

    dialogue_key: str = Field(min_length=1, description="Projection identity inside SourceDramaSnapshot")
    dialogue_group_id: str = Field(min_length=1, description="Canonical complete-utterance identity")
    projection_index: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1, description="Text visible in this Shot projection")
    speakers: list[str] = Field(default_factory=list, description="scene-local person_key references")

    @model_validator(mode="after")
    def _valid_range(self) -> "SourceDramaDialogueV1":
        if self.end_us < self.start_us:
            raise ValueError("dialogue projection end_us must be >= start_us")
        if len(set(self.speakers)) != len(self.speakers):
            raise ValueError("dialogue projection does not allow duplicate speakers")
        return self


class SourceDramaDialogueProjectionRefV1(_StrictSourceDramaModel):
    """Shot anchor retained by the canonical utterance for timing/reference-video use."""

    dialogue_key: str = Field(min_length=1)
    shot_key: str = Field(min_length=1)
    scene_key: str = Field(min_length=1)
    projection_index: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _valid_range(self) -> "SourceDramaDialogueProjectionRefV1":
        if self.end_us < self.start_us:
            raise ValueError("dialogue projection ref end_us must be >= start_us")
        return self


class SourceDramaDialogueUtteranceV1(_StrictSourceDramaModel):
    """Complete source-language dialogue business object consumed by localization/TTS."""

    dialogue_group_id: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)
    source_language: str | None = None
    speakers: list[str] = Field(default_factory=list, description="episode person_key references")
    projection_count: int = Field(ge=1)
    projections: list[SourceDramaDialogueProjectionRefV1] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_utterance(self) -> "SourceDramaDialogueUtteranceV1":
        if self.end_us < self.start_us:
            raise ValueError("source utterance end_us must be >= start_us")
        if self.projection_count != len(self.projections):
            raise ValueError("projection_count does not match utterance projections")
        indexes = [item.projection_index for item in self.projections]
        if indexes != list(range(1, len(self.projections) + 1)):
            raise ValueError("utterance projections must use contiguous projection_index values")
        keys = [item.dialogue_key for item in self.projections]
        if len(set(keys)) != len(keys):
            raise ValueError("utterance does not allow duplicate projection dialogue_key")
        if len(set(self.speakers)) != len(self.speakers):
            raise ValueError("utterance does not allow duplicate speakers")
        return self


class SourceDramaOnScreenTextV1(_StrictSourceDramaModel):
    text_key: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _valid_range(self) -> "SourceDramaOnScreenTextV1":
        if self.end_us < self.start_us:
            raise ValueError("on-screen text end_us must be >= start_us")
        return self


class SourceDramaObservedPropV1(_StrictSourceDramaModel):
    label: str = Field(min_length=1)
    interaction: str | None = None


class SourceDramaShotV1(_StrictSourceDramaModel):
    shot_key: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    source_shot_id: str | None = None
    source_revision_item_id: str | None = None
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    thumbnail_url: str | None = None
    reference_url: str | None = None
    visual_description: str | None = None
    people: list[str] = Field(default_factory=list, description="person_key references")
    performance: list[SourceDramaPerformanceV1] = Field(default_factory=list)
    source_dialogue: list[SourceDramaDialogueV1] = Field(default_factory=list, description="Shot dialogue projections")
    observed_props: list[SourceDramaObservedPropV1] = Field(default_factory=list)
    final_props: list[SourceDramaAssetRefV1] = Field(default_factory=list)
    cinematography: SceneTimelineCinematographyV1
    source_on_screen_text: list[SourceDramaOnScreenTextV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shot(self) -> "SourceDramaShotV1":
        if self.end_us < self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("Shot timing must satisfy duration_us = end_us - start_us")
        dialogue_keys = [item.dialogue_key for item in self.source_dialogue]
        text_keys = [item.text_key for item in self.source_on_screen_text]
        if len(set(dialogue_keys)) != len(dialogue_keys):
            raise ValueError("SourceDramaSnapshot does not allow duplicate dialogue_key in one Shot")
        if len(set(text_keys)) != len(text_keys):
            raise ValueError("SourceDramaSnapshot does not allow duplicate text_key in one Shot")
        if len(set(self.people)) != len(self.people):
            raise ValueError("SourceDramaSnapshot does not allow duplicate Shot people")
        prop_ids = [item.id for item in self.final_props]
        if len(set(prop_ids)) != len(prop_ids):
            raise ValueError("SourceDramaSnapshot does not allow duplicate Final Prop in one Shot")
        return self


class SourceDramaSceneV1(_StrictSourceDramaModel):
    scene_key: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    title: str = Field(min_length=1)
    story_summary: str | None = None
    scene_info: SceneTimelineSceneInfoV1
    final_scene: SourceDramaAssetRefV1 | None = None
    people: list[SourceDramaPersonV1] = Field(default_factory=list)
    shots: list[SourceDramaShotV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_scene(self) -> "SourceDramaSceneV1":
        if self.end_us < self.start_us or self.duration_us != self.end_us - self.start_us:
            raise ValueError("Scene timing must satisfy duration_us = end_us - start_us")
        person_keys = [item.person_key for item in self.people]
        if len(set(person_keys)) != len(person_keys):
            raise ValueError("SourceDramaSnapshot does not allow duplicate person_key in one Scene")
        valid_people = set(person_keys)
        for shot in self.shots:
            if not set(shot.people).issubset(valid_people):
                raise ValueError("Shot people must belong to the current Scene")
            for performance in shot.performance:
                if not set(performance.people).issubset(valid_people):
                    raise ValueError("Performance people must belong to the current Scene")
            for dialogue in shot.source_dialogue:
                if not set(dialogue.speakers).issubset(valid_people):
                    raise ValueError("Dialogue projection speakers must belong to the current Scene")
        return self


class SourceDramaEpisodeSnapshotV1(_StrictSourceDramaModel):
    schema_version: Literal["source-drama-snapshot-v1"] = SOURCE_DRAMA_SNAPSHOT_SCHEMA_VERSION
    status: Literal["READY", "READY_WITH_WARNINGS"]
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    episode_title: str = Field(min_length=1)
    episode_order: int = Field(ge=1)
    source_language: str = Field(min_length=1)
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    source_asset_revision_id: str | None = None
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    scene_count: int = Field(ge=0)
    shot_count: int = Field(ge=0)
    resolved_character_count: int = Field(ge=0)
    unresolved_person_count: int = Field(ge=0)
    source_dialogue_count: int = Field(ge=0, description="Canonical complete utterance count")
    source_dialogue_projection_count: int = Field(ge=0)
    source_on_screen_text_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    source_dialogue_utterances: list[SourceDramaDialogueUtteranceV1] = Field(default_factory=list)
    scenes: list[SourceDramaSceneV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _aggregate_counts_match(self) -> "SourceDramaEpisodeSnapshotV1":
        shots = [shot for scene in self.scenes for shot in scene.shots]
        people = [person for scene in self.scenes for person in scene.people]
        resolved_character_ids = {
            person.character.id for person in people if person.character is not None
        }
        unresolved = sum(person.character is None for person in people)
        projection_rows = [dialogue for shot in shots for dialogue in shot.source_dialogue]
        screen_text_count = sum(len(shot.source_on_screen_text) for shot in shots)
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count does not match SourceDramaSnapshot scenes")
        if self.shot_count != len(shots):
            raise ValueError("shot_count does not match SourceDramaSnapshot shots")
        if self.resolved_character_count != len(resolved_character_ids):
            raise ValueError("resolved_character_count does not match unique resolved Characters")
        if self.unresolved_person_count != unresolved:
            raise ValueError("unresolved_person_count does not match unresolved scene people")
        if self.source_dialogue_count != len(self.source_dialogue_utterances):
            raise ValueError("source_dialogue_count does not match complete source utterances")
        if self.source_dialogue_projection_count != len(projection_rows):
            raise ValueError("source_dialogue_projection_count does not match Shot projections")
        if self.source_on_screen_text_count != screen_text_count:
            raise ValueError("source_on_screen_text_count does not match source_on_screen_text")
        if len({scene.scene_key for scene in self.scenes}) != len(self.scenes):
            raise ValueError("SourceDramaSnapshot does not allow duplicate scene_key")
        if len({shot.shot_key for shot in shots}) != len(shots):
            raise ValueError("SourceDramaSnapshot does not allow duplicate shot_key")

        episode_people = {person.person_key for person in people}
        utterance_by_group = {item.dialogue_group_id: item for item in self.source_dialogue_utterances}
        if len(utterance_by_group) != len(self.source_dialogue_utterances):
            raise ValueError("SourceDramaSnapshot does not allow duplicate dialogue_group_id")
        projection_by_key = {item.dialogue_key: item for item in projection_rows}
        if len(projection_by_key) != len(projection_rows):
            raise ValueError("SourceDramaSnapshot does not allow duplicate dialogue projection keys")
        if any(not set(item.speakers).issubset(episode_people) for item in self.source_dialogue_utterances):
            raise ValueError("Utterance speakers must belong to the current Episode")

        referenced_projection_keys: set[str] = set()
        for utterance in self.source_dialogue_utterances:
            for ref in utterance.projections:
                projection = projection_by_key.get(ref.dialogue_key)
                if projection is None:
                    raise ValueError("Utterance projection reference is missing from Shot source_dialogue")
                if projection.dialogue_group_id != utterance.dialogue_group_id:
                    raise ValueError("Utterance projection references another dialogue_group_id")
                if projection.projection_index != ref.projection_index:
                    raise ValueError("Utterance projection_index does not match Shot projection")
                if projection.start_us != ref.start_us or projection.end_us != ref.end_us or projection.source_text != ref.source_text:
                    raise ValueError("Utterance projection facts do not match Shot projection")
                referenced_projection_keys.add(ref.dialogue_key)
        if referenced_projection_keys != set(projection_by_key):
            raise ValueError("Every Shot dialogue projection must belong to exactly one utterance")

        if self.status == "READY" and self.warnings:
            raise ValueError("READY SourceDramaSnapshot must not contain warnings")
        if self.status == "READY_WITH_WARNINGS" and not self.warnings:
            raise ValueError("READY_WITH_WARNINGS SourceDramaSnapshot must explain warnings")
        return self


class SourceDramaProjectSnapshotV1(_StrictSourceDramaModel):
    schema_version: Literal["source-drama-project-snapshot-v1"] = SOURCE_DRAMA_PROJECT_SCHEMA_VERSION
    status: Literal["READY", "READY_WITH_WARNINGS"]
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    source_language: str = Field(min_length=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_count: int = Field(ge=0)
    scene_count: int = Field(ge=0)
    shot_count: int = Field(ge=0)
    resolved_character_count: int = Field(ge=0)
    source_dialogue_count: int = Field(ge=0, description="Canonical complete utterance count")
    source_dialogue_projection_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    characters: list[SourceDramaAssetRefV1] = Field(default_factory=list)
    episodes: list[SourceDramaEpisodeSnapshotV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _aggregate_project(self) -> "SourceDramaProjectSnapshotV1":
        if self.episode_count != len(self.episodes):
            raise ValueError("episode_count does not match SourceDramaProjectSnapshot episodes")
        if self.scene_count != sum(item.scene_count for item in self.episodes):
            raise ValueError("scene_count does not match episode snapshots")
        if self.shot_count != sum(item.shot_count for item in self.episodes):
            raise ValueError("shot_count does not match episode snapshots")
        if self.source_dialogue_count != sum(item.source_dialogue_count for item in self.episodes):
            raise ValueError("source_dialogue_count does not match episode utterances")
        if self.source_dialogue_projection_count != sum(item.source_dialogue_projection_count for item in self.episodes):
            raise ValueError("source_dialogue_projection_count does not match episode projections")
        if self.resolved_character_count != len(self.characters):
            raise ValueError("resolved_character_count does not match project character catalog")
        character_ids = [item.id for item in self.characters]
        if len(set(character_ids)) != len(character_ids):
            raise ValueError("SourceDramaProjectSnapshot does not allow duplicate Characters")
        episode_ids = [item.episode_id for item in self.episodes]
        if len(set(episode_ids)) != len(episode_ids):
            raise ValueError("SourceDramaProjectSnapshot does not allow duplicate Episodes")
        if self.status == "READY" and self.warnings:
            raise ValueError("READY SourceDramaProjectSnapshot must not contain warnings")
        if self.status == "READY_WITH_WARNINGS" and not self.warnings:
            raise ValueError("READY_WITH_WARNINGS SourceDramaProjectSnapshot must explain warnings")
        return self


__all__ = [
    "SOURCE_DRAMA_PROJECT_SCHEMA_VERSION",
    "SOURCE_DRAMA_SNAPSHOT_SCHEMA_VERSION",
    "SourceDramaAssetRefV1",
    "SourceDramaDialogueProjectionRefV1",
    "SourceDramaDialogueUtteranceV1",
    "SourceDramaDialogueV1",
    "SourceDramaEpisodeSnapshotV1",
    "SourceDramaObservedPropV1",
    "SourceDramaOnScreenTextV1",
    "SourceDramaPerformanceV1",
    "SourceDramaPersonV1",
    "SourceDramaProjectSnapshotV1",
    "SourceDramaSceneV1",
    "SourceDramaShotV1",
]
