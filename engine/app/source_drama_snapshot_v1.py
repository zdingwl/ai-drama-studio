"""Compose the stable SourceDramaSnapshot from current source truth.

Implementation note: V1 intentionally consumes the existing P6 read model while the old
Breakdown layers remain frozen. Downstream remake code must depend on this module/contract,
not on P5/P6/P7 names. This creates a migration boundary without reopening accepted video
understanding or Character identity logic.

Dialogue is materialized at two levels:
- Shot ``source_dialogue`` keeps the exact source-time projection used by video/timing logic.
- Episode ``source_dialogue_utterances`` groups projections by ``dialogue_group_id`` and is
  the only dialogue list that target translation/TTS should consume.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1
from engine.app.breakdown_read_model_v1 import load_episode_breakdown_read_model_v1
from engine.app.shot_revision_v2 import ShotRevisionItem
from engine.app.source_dialogue_speaker_override_v1 import (
    load_episode_source_dialogue_speaker_overrides_v1,
    source_dialogue_signature_v1,
)
from engine.app.source_dialogue_speaker_resolver_v1 import resolve_shot_dialogue_speakers_v1
from engine.app.source_drama_snapshot_contract_v1 import (
    SourceDramaAssetRefV1,
    SourceDramaEpisodeSnapshotV1,
    SourceDramaProjectSnapshotV1,
)
from engine.app.studio_v2 import Episode, Project, get_session


class SourceDramaSnapshotError(RuntimeError):
    """Current source truth cannot be safely exposed as a remake snapshot."""


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _asset(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return SourceDramaAssetRefV1(
        id=value.id,
        name=value.name,
        cover_url=value.cover_url,
    ).model_dump(mode="json")


def _canonical_fingerprint(payload: Mapping[str, Any], *, omit: set[str]) -> str:
    canonical = {key: value for key, value in payload.items() if key not in omit}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_drama_episode_fingerprint(payload: Mapping[str, Any]) -> str:
    """Fingerprint only source facts/anchors; operational status/warnings do not change identity."""

    return _canonical_fingerprint(
        payload,
        omit={"source_fingerprint", "status", "warnings"},
    )


def source_drama_project_fingerprint(payload: Mapping[str, Any]) -> str:
    return _canonical_fingerprint(
        payload,
        omit={"source_fingerprint", "status", "warnings"},
    )


def _legacy_dialogue_group_id(
    breakdown_run_id: str,
    shot_ordinal: int,
    dialogue_index: int,
) -> str:
    """Fail-safe identity for historical SceneTimeline payloads created before dialogue grouping.

    It intentionally never merges two old projections. New SceneTimeline assembly emits a
    real group ID from the ASR segment anchor, so current production data can express N-shot
    projection of one complete utterance without a database migration.
    """

    return f"{breakdown_run_id}:DG:LEGACY:H{shot_ordinal}:D{dialogue_index}"


def _join_utterance_projection_texts(
    projections: list[Mapping[str, Any]],
    *,
    source_language: str | None,
) -> str:
    """Deterministically reconstruct the complete source utterance from its Shot projections.

    Fusion's no-word-timing fallback copies the full segment text to every intersecting Shot;
    an all-equal group is therefore one copy, never repeated N times. Word-timestamp splits
    are concatenated in source-time order. CJK languages do not receive an artificial space;
    space-delimited languages receive one boundary space because projection text is trimmed
    at Shot boundaries by the existing Fusion layer.
    """

    pieces = [str(item.get("source_text") or "") for item in projections]
    pieces = [item for item in pieces if item.strip()]
    if not pieces:
        raise SourceDramaSnapshotError("完整源对白没有可用文本")
    if all(item == pieces[0] for item in pieces[1:]):
        return pieces[0]

    normalized_language = str(source_language or "").strip().lower()
    compact_boundary = normalized_language.startswith(("zh", "ja", "ko"))
    stripped = [item.strip() for item in pieces]
    return ("" if compact_boundary else " ").join(stripped)


def _canonical_utterances(
    projection_records: list[dict[str, Any]],
    *,
    default_source_language: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in projection_records:
        group_id = str(record["dialogue"]["dialogue_group_id"])
        grouped.setdefault(group_id, []).append(record)

    utterances: list[dict[str, Any]] = []
    for group_id, records in grouped.items():
        records.sort(key=lambda item: (
            int(item["dialogue"]["start_us"]),
            int(item["dialogue"]["end_us"]),
            int(item["shot_ordinal"]),
            str(item["dialogue"]["dialogue_key"]),
        ))
        language_values = _dedupe([
            str(item.get("source_language") or "") for item in records
        ])
        language = language_values[0] if len(language_values) == 1 else default_source_language

        speakers: list[str] = []
        projections: list[dict[str, Any]] = []
        for projection_index, record in enumerate(records, start=1):
            dialogue = record["dialogue"]
            dialogue["projection_index"] = projection_index
            for speaker in dialogue.get("speakers") or []:
                speaker_key = str(speaker)
                if speaker_key and speaker_key not in speakers:
                    speakers.append(speaker_key)
            projections.append({
                "dialogue_key": str(dialogue["dialogue_key"]),
                "shot_key": str(record["shot_key"]),
                "scene_key": str(record["scene_key"]),
                "projection_index": projection_index,
                "start_us": int(dialogue["start_us"]),
                "end_us": int(dialogue["end_us"]),
                "source_text": str(dialogue["source_text"]),
            })

        utterances.append({
            "dialogue_group_id": group_id,
            "start_us": min(int(item["dialogue"]["start_us"]) for item in records),
            "end_us": max(int(item["dialogue"]["end_us"]) for item in records),
            "source_text": _join_utterance_projection_texts(
                [item["dialogue"] for item in records],
                source_language=language,
            ),
            "source_language": language or None,
            "speakers": speakers,
            "projection_count": len(projections),
            "projections": projections,
        })

    utterances.sort(key=lambda item: (
        int(item["start_us"]),
        int(item["end_us"]),
        str(item["dialogue_group_id"]),
    ))
    return utterances


def compose_episode_source_drama_snapshot_v1(
    read_model_payload: Mapping[str, Any] | BreakdownReadModelV1,
    *,
    project_id: str,
    episode_id: str,
    episode_title: str,
    episode_order: int,
    source_language: str,
    revision_items_by_ordinal: Mapping[int, ShotRevisionItem] | None = None,
    speaker_overrides: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Pure composition from one current P6 read model into product-facing source truth."""

    read_model = (
        read_model_payload
        if isinstance(read_model_payload, BreakdownReadModelV1)
        else BreakdownReadModelV1.model_validate(read_model_payload)
    )
    timeline = read_model.timeline
    if timeline.episode_id != episode_id:
        raise SourceDramaSnapshotError("Breakdown read model belongs to another Episode")
    if not timeline.is_current:
        raise SourceDramaSnapshotError("SourceDramaSnapshot only consumes the current Breakdown result")

    identity_by_scene = {item.scene_ordinal: item for item in read_model.identity.scenes}
    if len(identity_by_scene) != len(read_model.identity.scenes):
        raise SourceDramaSnapshotError("Character identity overlay contains duplicate Scene ordinals")
    if set(identity_by_scene) != {scene.ordinal for scene in timeline.scenes}:
        raise SourceDramaSnapshotError("Character identity overlay does not match Scene Timeline")

    asset_scene_by_ordinal: dict[int, Any] = {}
    asset_shot_by_key: dict[tuple[int, int], Any] = {}
    asset_warnings: list[str] = []
    asset_revision_id = read_model.identity.asset_revision_id
    if read_model.assets is not None:
        assets = read_model.assets
        if asset_revision_id and assets.asset_revision_id and asset_revision_id != assets.asset_revision_id:
            raise SourceDramaSnapshotError("Character and Scene/Prop overlays use different AssetRevision values")
        asset_revision_id = asset_revision_id or assets.asset_revision_id
        asset_warnings = list(assets.warnings)
        asset_scene_by_ordinal = {item.scene_ordinal: item for item in assets.scenes}
        asset_shot_by_key = {(item.scene_ordinal, item.shot_ordinal): item for item in assets.shots}
        if len(asset_scene_by_ordinal) != len(assets.scenes):
            raise SourceDramaSnapshotError("Final Scene overlay contains duplicate Scene ordinals")
        if len(asset_shot_by_key) != len(assets.shots):
            raise SourceDramaSnapshotError("Final Prop overlay contains duplicate Shot keys")

    revision_items = dict(revision_items_by_ordinal or {})
    speaker_override_map = dict(speaker_overrides or {})
    scenes: list[dict[str, Any]] = []
    dialogue_projection_records: list[dict[str, Any]] = []
    unresolved_people = 0
    resolved_character_ids: set[str] = set()
    on_screen_text_count = 0
    missing_revision_item_count = 0
    missing_reference_count = 0
    legacy_dialogue_group_count = 0

    for scene in timeline.scenes:
        identity_scene = identity_by_scene[scene.ordinal]
        identity_people = {person.ref: person for person in identity_scene.people}
        timeline_people = {person.ref: person for person in scene.people}
        if len(identity_people) != len(identity_scene.people) or set(identity_people) != set(timeline_people):
            raise SourceDramaSnapshotError("Scene Character overlay does not match source people")

        scene_key = f"{episode_id}:{timeline.source_breakdown_run_id}:S{scene.ordinal}"
        people_rows: list[dict[str, Any]] = []
        person_key_by_ref: dict[str, str] = {}
        for person in scene.people:
            display = identity_people[person.ref]
            person_key = f"{scene_key}:{person.ref}"
            person_key_by_ref[person.ref] = person_key
            character = _asset(display.character)
            if character is None:
                unresolved_people += 1
            else:
                resolved_character_ids.add(str(character["id"]))
            people_rows.append({
                "person_key": person_key,
                "scene_person_ref": person.ref,
                "display_name": display.display_name,
                "appearance": person.appearance,
                "character": character,
            })

        scene_person_keys = set(person_key_by_ref.values())
        shot_rows: list[dict[str, Any]] = []
        for shot in scene.shots:
            item = revision_items.get(shot.ordinal)
            if item is None:
                missing_revision_item_count += 1
            shot_key = f"{episode_id}:{timeline.source_shot_revision_id}:H{shot.ordinal}"
            if not shot.reference_url:
                missing_reference_count += 1

            shot_people = [person_key_by_ref[ref] for ref in shot.people if ref in person_key_by_ref]
            performance_rows = [
                {
                    "text": performance.text,
                    "people": [person_key_by_ref[ref] for ref in performance.people if ref in person_key_by_ref],
                }
                for performance in shot.performance
            ]
            dialogue_inputs: list[dict[str, Any]] = []
            dialogue_languages: list[str | None] = []
            for index, dialogue in enumerate(shot.dialogue, start=1):
                group_id = str(getattr(dialogue, "dialogue_group_id", None) or "").strip()
                if not group_id:
                    legacy_dialogue_group_count += 1
                    group_id = _legacy_dialogue_group_id(
                        timeline.source_breakdown_run_id,
                        shot.ordinal,
                        index,
                    )
                dialogue_inputs.append({
                    "dialogue_key": f"{shot_key}:D{index}",
                    "dialogue_group_id": group_id,
                    # Reassigned after all Shot projections have been grouped.
                    "projection_index": 1,
                    "start_us": dialogue.start_us,
                    "end_us": dialogue.end_us,
                    "source_text": dialogue.text,
                    "speakers": [person_key_by_ref[ref] for ref in dialogue.speakers if ref in person_key_by_ref],
                })
                dialogue_languages.append(str(getattr(dialogue, "source_language", None) or "").strip() or None)

            for dialogue in dialogue_inputs:
                override = speaker_override_map.get(str(dialogue["dialogue_key"]))
                if not isinstance(override, Mapping):
                    continue
                person_key = str(override.get("person_key") or "").strip()
                dialogue_signature = str(override.get("dialogue_signature") or "").strip()
                if person_key not in scene_person_keys:
                    continue
                if dialogue_signature != source_dialogue_signature_v1(dialogue):
                    continue
                dialogue["speakers"] = [person_key]

            speaker_resolutions = resolve_shot_dialogue_speakers_v1(
                dialogue_inputs,
                scene_people=people_rows,
                shot_people=shot_people,
                performance=performance_rows,
            )
            dialogue_rows = [
                {
                    **dialogue,
                    "speakers": list(speaker_resolutions[index].speaker_keys),
                }
                for index, dialogue in enumerate(dialogue_inputs)
            ]
            for index, dialogue in enumerate(dialogue_rows):
                dialogue_projection_records.append({
                    "scene_key": scene_key,
                    "shot_key": shot_key,
                    "shot_ordinal": shot.ordinal,
                    "source_language": dialogue_languages[index],
                    "dialogue": dialogue,
                })

            text_rows = [
                {
                    "text_key": f"{shot_key}:T{index}",
                    "start_us": text.start_us,
                    "end_us": text.end_us,
                    "source_text": text.text,
                }
                for index, text in enumerate(shot.on_screen_text, start=1)
            ]
            on_screen_text_count += len(text_rows)

            asset_shot = asset_shot_by_key.get((scene.ordinal, shot.ordinal))
            shot_rows.append({
                "shot_key": shot_key,
                "ordinal": shot.ordinal,
                "source_shot_id": item.original_shot_id if item is not None else None,
                "source_revision_item_id": item.id if item is not None else None,
                "start_us": shot.start_us,
                "end_us": shot.end_us,
                "duration_us": shot.duration_us,
                "thumbnail_url": shot.thumbnail_url,
                "reference_url": shot.reference_url,
                "visual_description": shot.visual_description,
                "people": shot_people,
                "performance": performance_rows,
                "source_dialogue": dialogue_rows,
                "observed_props": [
                    {"label": prop.label, "interaction": prop.interaction}
                    for prop in shot.props
                ],
                "final_props": [_asset(prop) for prop in (asset_shot.props if asset_shot else [])],
                "cinematography": shot.cinematography.model_dump(mode="json"),
                "source_on_screen_text": text_rows,
            })

        asset_scene = asset_scene_by_ordinal.get(scene.ordinal)
        scenes.append({
            "scene_key": scene_key,
            "ordinal": scene.ordinal,
            "start_us": scene.start_us,
            "end_us": scene.end_us,
            "duration_us": scene.duration_us,
            "title": scene.title,
            "story_summary": scene.story_summary,
            "scene_info": scene.scene_info.model_dump(mode="json"),
            "final_scene": _asset(asset_scene.scene) if asset_scene and asset_scene.scene else None,
            "people": people_rows,
            "shots": shot_rows,
        })

    utterances = _canonical_utterances(
        dialogue_projection_records,
        default_source_language=source_language,
    )

    warnings = _dedupe(list(timeline.warnings) + list(read_model.identity.warnings) + asset_warnings)
    if unresolved_people:
        warnings.append(f"{unresolved_people} 个 Scene-local 人物尚未安全解析到 Final Character")
    if missing_revision_item_count:
        warnings.append(f"{missing_revision_item_count} 个 Shot 缺少源 ShotRevisionItem 映射")
    if missing_reference_count:
        warnings.append(f"{missing_reference_count} 个 Shot 缺少 Reference Video")
    if legacy_dialogue_group_count:
        warnings.append(
            f"{legacy_dialogue_group_count} 个历史对白投影缺少 dialogue_group_id，"
            "已按单投影保守处理；重新生成当前 Scene Timeline 后可获得完整对白分组"
        )
    warnings = _dedupe(warnings)

    payload: dict[str, Any] = {
        "schema_version": "source-drama-snapshot-v1",
        "status": "READY_WITH_WARNINGS" if warnings else "READY",
        "project_id": project_id,
        "episode_id": episode_id,
        "episode_title": episode_title,
        "episode_order": episode_order,
        "source_language": source_language,
        "source_breakdown_run_id": timeline.source_breakdown_run_id,
        "source_shot_revision_id": timeline.source_shot_revision_id,
        "source_asset_revision_id": asset_revision_id,
        "source_fingerprint": "0" * 64,
        "scene_count": len(scenes),
        "shot_count": sum(len(scene["shots"]) for scene in scenes),
        "resolved_character_count": len(resolved_character_ids),
        "unresolved_person_count": unresolved_people,
        "source_dialogue_count": len(utterances),
        "source_dialogue_projection_count": len(dialogue_projection_records),
        "source_on_screen_text_count": on_screen_text_count,
        "warnings": warnings,
        "source_dialogue_utterances": utterances,
        "scenes": scenes,
    }
    payload["source_fingerprint"] = source_drama_episode_fingerprint(payload)
    return SourceDramaEpisodeSnapshotV1.model_validate(payload).model_dump(mode="json")


def load_episode_source_drama_snapshot_v1(episode_id: str) -> dict[str, Any] | None:
    read_model_raw = load_episode_breakdown_read_model_v1(episode_id)
    if read_model_raw is None:
        return None
    read_model = BreakdownReadModelV1.model_validate(read_model_raw)
    speaker_overrides = load_episode_source_dialogue_speaker_overrides_v1(episode_id)

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        project = session.get(Project, episode.project_id)
        if project is None:
            raise LookupError("Project 不存在")
        items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == read_model.timeline.source_shot_revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        item_map = {item.ordinal: item for item in items}
        return compose_episode_source_drama_snapshot_v1(
            read_model,
            project_id=project.id,
            episode_id=episode.id,
            episode_title=episode.title,
            episode_order=episode.sort_order,
            source_language=project.source_language,
            revision_items_by_ordinal=item_map,
            speaker_overrides=speaker_overrides,
        )


def compose_project_source_drama_snapshot_v1(
    *,
    project_id: str,
    project_name: str,
    source_language: str,
    episodes: list[Mapping[str, Any] | SourceDramaEpisodeSnapshotV1],
) -> dict[str, Any]:
    parsed = [
        item if isinstance(item, SourceDramaEpisodeSnapshotV1) else SourceDramaEpisodeSnapshotV1.model_validate(item)
        for item in episodes
    ]
    parsed.sort(key=lambda item: item.episode_order)
    if any(item.project_id != project_id for item in parsed):
        raise SourceDramaSnapshotError("Episode snapshot belongs to another Project")
    if any(item.source_language != source_language for item in parsed):
        raise SourceDramaSnapshotError("Episode snapshot source language does not match Project")

    character_by_id: dict[str, SourceDramaAssetRefV1] = {}
    warnings: list[str] = []
    for episode in parsed:
        warnings.extend(f"第{episode.episode_order:02d}集：{warning}" for warning in episode.warnings)
        for scene in episode.scenes:
            for person in scene.people:
                if person.character is not None:
                    character_by_id.setdefault(person.character.id, person.character)

    characters = [character_by_id[key] for key in sorted(character_by_id)]
    warnings = _dedupe(warnings)
    payload: dict[str, Any] = {
        "schema_version": "source-drama-project-snapshot-v1",
        "status": "READY_WITH_WARNINGS" if warnings else "READY",
        "project_id": project_id,
        "project_name": project_name,
        "source_language": source_language,
        "source_fingerprint": "0" * 64,
        "episode_count": len(parsed),
        "scene_count": sum(item.scene_count for item in parsed),
        "shot_count": sum(item.shot_count for item in parsed),
        "resolved_character_count": len(characters),
        "source_dialogue_count": sum(item.source_dialogue_count for item in parsed),
        "source_dialogue_projection_count": sum(item.source_dialogue_projection_count for item in parsed),
        "warnings": warnings,
        "characters": [item.model_dump(mode="json") for item in characters],
        "episodes": [item.model_dump(mode="json") for item in parsed],
    }
    payload["source_fingerprint"] = source_drama_project_fingerprint(payload)
    return SourceDramaProjectSnapshotV1.model_validate(payload).model_dump(mode="json")


def load_project_source_drama_snapshot_v1(project_id: str) -> dict[str, Any]:
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("Project 不存在")
        episode_ids = list(session.scalars(
            select(Episode.id).where(Episode.project_id == project_id).order_by(Episode.sort_order)
        ).all())
        project_name = project.name
        source_language = project.source_language

    if not episode_ids:
        raise SourceDramaSnapshotError("项目还没有剧集")

    snapshots: list[dict[str, Any]] = []
    missing: list[str] = []
    for episode_id in episode_ids:
        snapshot = load_episode_source_drama_snapshot_v1(episode_id)
        if snapshot is None:
            missing.append(episode_id)
        else:
            snapshots.append(snapshot)
    if missing:
        raise SourceDramaSnapshotError(
            f"{len(missing)} 个 Episode 尚未形成当前 SourceDramaSnapshot"
        )

    return compose_project_source_drama_snapshot_v1(
        project_id=project_id,
        project_name=project_name,
        source_language=source_language,
        episodes=snapshots,
    )


__all__ = [
    "SourceDramaSnapshotError",
    "compose_episode_source_drama_snapshot_v1",
    "compose_project_source_drama_snapshot_v1",
    "load_episode_source_drama_snapshot_v1",
    "load_project_source_drama_snapshot_v1",
    "source_drama_episode_fingerprint",
    "source_drama_project_fingerprint",
]
