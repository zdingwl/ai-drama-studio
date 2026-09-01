"""P7.1 deterministic localization source-package assembler.

Authority flows only from the current P6 read model. This module does not translate,
rewrite, infer identity, or persist localization copy.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1, BreakdownReadPersonV1
from engine.app.breakdown_read_model_v1 import load_episode_breakdown_read_model_v1
from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1, LocalizationSourcePersonV1
from engine.app.studio_v2 import Episode, Project, get_session


class LocalizationSourceError(RuntimeError):
    """P7.1 cannot safely construct a source package from current truth."""


def _warnings(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for group in groups for item in group if item.strip()))


def _person_display(person: BreakdownReadPersonV1) -> LocalizationSourcePersonV1:
    return LocalizationSourcePersonV1(
        display_name=person.display_name,
        character=person.character,
    )


def compose_localization_source_v1(
    read_model_payload: Mapping[str, Any] | BreakdownReadModelV1,
    *,
    project_id: str,
    source_language: str,
    target_language: str,
    target_region: str,
) -> dict[str, Any]:
    """Create one immutable, version-anchored source handoff from P6."""

    read_model = (
        read_model_payload
        if isinstance(read_model_payload, BreakdownReadModelV1)
        else BreakdownReadModelV1.model_validate(read_model_payload)
    )
    timeline = read_model.timeline
    if not timeline.is_current:
        raise LocalizationSourceError("P7 只允许消费 current Breakdown read model")

    identity_by_scene = {item.scene_ordinal: item for item in read_model.identity.scenes}
    if len(identity_by_scene) != len(read_model.identity.scenes):
        raise LocalizationSourceError("P6 identity Scene surface 重复")
    if set(identity_by_scene) != {scene.ordinal for scene in timeline.scenes}:
        raise LocalizationSourceError("P6 identity Scene surface 与 Timeline 不一致")

    asset_scene_by_ordinal: dict[int, Any] = {}
    asset_shot_by_key: dict[tuple[int, int], Any] = {}
    asset_revision_id = read_model.identity.asset_revision_id
    asset_warnings: list[str] = []
    if read_model.assets is not None:
        assets = read_model.assets
        asset_warnings = assets.warnings
        if asset_revision_id and assets.asset_revision_id and asset_revision_id != assets.asset_revision_id:
            raise LocalizationSourceError("P6 Character 与 Scene/Prop AssetRevision 不一致")
        asset_revision_id = asset_revision_id or assets.asset_revision_id
        asset_scene_by_ordinal = {item.scene_ordinal: item for item in assets.scenes}
        asset_shot_by_key = {(item.scene_ordinal, item.shot_ordinal): item for item in assets.shots}
        if len(asset_scene_by_ordinal) != len(assets.scenes):
            raise LocalizationSourceError("P6 Final Scene surface 重复")
        if len(asset_shot_by_key) != len(assets.shots):
            raise LocalizationSourceError("P6 Final Prop Shot surface 重复")
        expected_scene_ordinals = {scene.ordinal for scene in timeline.scenes}
        expected_shot_keys = {
            (scene.ordinal, shot.ordinal)
            for scene in timeline.scenes
            for shot in scene.shots
        }
        if set(asset_scene_by_ordinal) != expected_scene_ordinals:
            raise LocalizationSourceError("P6 Final Scene surface 与 Timeline 不一致")
        if set(asset_shot_by_key) != expected_shot_keys:
            raise LocalizationSourceError("P6 Final Prop Shot surface 与 Timeline 不一致")

    scenes: list[dict[str, Any]] = []
    dialogue_count = 0
    screen_text_count = 0

    for scene in timeline.scenes:
        identity_scene = identity_by_scene[scene.ordinal]
        identity_people = {person.ref: person for person in identity_scene.people}
        timeline_people = {person.ref: person for person in scene.people}
        if len(identity_people) != len(identity_scene.people) or set(identity_people) != set(timeline_people):
            raise LocalizationSourceError("P6 Scene 人物 surface 与 Timeline 不一致")
        for ref, source_person in timeline_people.items():
            display = identity_people[ref]
            if display.character is None and display.display_name != source_person.display_name:
                raise LocalizationSourceError("匿名人物显示被下游改写")
            if display.character is not None and display.display_name != display.character.name:
                raise LocalizationSourceError("Final Character 名称与人物显示不一致")

        def people_for_refs(refs: list[str]) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for ref in refs:
                person = identity_people.get(ref)
                if person is None:
                    raise LocalizationSourceError("Shot 人物引用不属于当前 Scene")
                rows.append(_person_display(person).model_dump(mode="json"))
            return rows

        scene_asset = asset_scene_by_ordinal.get(scene.ordinal)
        shot_rows: list[dict[str, Any]] = []
        for shot in scene.shots:
            shot_asset = asset_shot_by_key.get((scene.ordinal, shot.ordinal))
            source_dialogue: list[dict[str, Any]] = []
            for index, item in enumerate(shot.dialogue, start=1):
                source_dialogue.append({
                    "source_key": f"S{scene.ordinal}:H{shot.ordinal}:D{index}",
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "source_text": item.text,
                    "speakers": people_for_refs(item.speakers),
                })
            source_on_screen_text = [
                {
                    "source_key": f"S{scene.ordinal}:H{shot.ordinal}:T{index}",
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "source_text": item.text,
                }
                for index, item in enumerate(shot.on_screen_text, start=1)
            ]
            dialogue_count += len(source_dialogue)
            screen_text_count += len(source_on_screen_text)
            shot_rows.append({
                "ordinal": shot.ordinal,
                "start_us": shot.start_us,
                "end_us": shot.end_us,
                "duration_us": shot.duration_us,
                "thumbnail_url": shot.thumbnail_url,
                "reference_url": shot.reference_url,
                "visual_description": shot.visual_description,
                "people": people_for_refs(shot.people),
                "performance": [
                    {"text": item.text, "people": people_for_refs(item.people)}
                    for item in shot.performance
                ],
                "source_dialogue": source_dialogue,
                "observed_props": [
                    {"label": item.label, "interaction": item.interaction}
                    for item in shot.props
                ],
                "final_props": [
                    item.model_dump(mode="json") for item in (shot_asset.props if shot_asset else [])
                ],
                "cinematography": shot.cinematography.model_dump(mode="json"),
                "source_on_screen_text": source_on_screen_text,
            })

        scenes.append({
            "ordinal": scene.ordinal,
            "start_us": scene.start_us,
            "end_us": scene.end_us,
            "duration_us": scene.duration_us,
            "title": scene.title,
            "story_summary": scene.story_summary,
            "scene_info": scene.scene_info.model_dump(mode="json"),
            "final_scene": scene_asset.scene.model_dump(mode="json") if scene_asset and scene_asset.scene else None,
            "people": [_person_display(identity_people[person.ref]).model_dump(mode="json") for person in scene.people],
            "shots": shot_rows,
        })

    warnings = _warnings(timeline.warnings, read_model.identity.warnings, asset_warnings)
    result = LocalizationSourcePackageV1(
        status="READY_WITH_WARNINGS" if warnings else "READY",
        project_id=project_id,
        episode_id=timeline.episode_id,
        source_language=source_language,
        target_language=target_language,
        target_region=target_region,
        source_breakdown_run_id=timeline.source_breakdown_run_id,
        source_shot_revision_id=timeline.source_shot_revision_id,
        source_asset_revision_id=asset_revision_id,
        scene_count=len(scenes),
        shot_count=sum(len(scene["shots"]) for scene in scenes),
        source_dialogue_count=dialogue_count,
        source_on_screen_text_count=screen_text_count,
        warnings=warnings,
        scenes=scenes,
    )
    return result.model_dump(mode="json")


def load_episode_localization_source_v1(episode_id: str) -> dict[str, Any] | None:
    """Load current P6 and package it with the Project localization target."""

    read_model_raw = load_episode_breakdown_read_model_v1(episode_id)
    if read_model_raw is None:
        return None

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        project = session.get(Project, episode.project_id)
        if project is None:
            raise LookupError("Project 不存在")
        return compose_localization_source_v1(
            read_model_raw,
            project_id=project.id,
            source_language=project.source_language,
            target_language=project.target_language,
            target_region=project.target_region,
        )


__all__ = [
    "LocalizationSourceError",
    "compose_localization_source_v1",
    "load_episode_localization_source_v1",
]
