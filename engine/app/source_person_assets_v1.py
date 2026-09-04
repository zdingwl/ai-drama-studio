"""原片人物资产归并。

业务事实边界：
- Breakdown / Character V10.1 只提供人物观察和身份 Evidence；
- Character 是项目级原片人物资产；
- ShotCharacterBinding 是人物是否出现在某个 Shot 的唯一 Final Binding；
- source_person_mappings_v1 只保存人工确认过的“观察 -> 人物资产”映射与定位证据，
  不另建第二套人物或 Shot Binding 事实。

当已有 Final ShotCharacterBinding 能对一个人物观察形成唯一交集时，系统会给出安全归并建议。
该建议本身不在 GET 时写库；只有用户显式保存时才写映射并创建 AssetRevision。
"""
from __future__ import annotations

import hashlib
import json
import math
from threading import RLock
from typing import Any

from sqlalchemy import select

from engine.app.asset_workspace_v3 import ShotCharacterBinding, _current_revision, _manual_revision
from engine.app.breakdown_scene_timeline_result_v1 import build_scene_timeline_result_v1
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.studio_v2 import Character, Episode, Shot, get_session, new_id

LOCK = RLock()
MAPPING_KEY = "source_person_mappings_v1"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def observations(episode_id: str, timeline: dict[str, Any], shot_ids: dict[int, str]) -> list[dict[str, Any]]:
    """把拉片中的局部人物整理成可归并观察，但不把 LocalSubject 当全局身份。"""

    rows: list[dict[str, Any]] = []
    for scene in timeline["scenes"]:
        for person in scene["people"]:
            appearances = [shot for shot in scene["shots"] if person["ref"] in shot["people"]]
            key = f'{episode_id}:{scene["ordinal"]}:{person["ref"]}'
            anchor = digest({
                "run": timeline["source_breakdown_run_id"],
                "revision": timeline["source_shot_revision_id"],
                "person": person,
                "shots": [(shot["ordinal"], shot["start_us"], shot["end_us"]) for shot in appearances],
            })
            rows.append({
                "key": key,
                "anchor": anchor,
                "episode_id": episode_id,
                "scene_ordinal": scene["ordinal"],
                "ref": person["ref"],
                "name": person["display_name"],
                "appearance": person.get("appearance"),
                "scene": scene["title"],
                "shots": [
                    {
                        "id": shot_ids[shot["ordinal"]],
                        "ordinal": shot["ordinal"],
                        "thumbnail_url": shot.get("thumbnail_url"),
                    }
                    for shot in appearances
                    if shot["ordinal"] in shot_ids
                ],
            })
    return rows


def _character_payload(
    character: Character,
    metadata: dict[str, Any],
    shot_ids: list[str],
    episode_by_shot: dict[str, str],
) -> dict[str, Any]:
    unique_shots = sorted(set(shot_ids))
    return {
        "id": character.id,
        "name": character.name,
        "status": character.status,
        "cover_url": metadata.get("cover_url"),
        "source_candidate_ids": list(metadata.get("source_candidate_ids") or []),
        "confidence": metadata.get("confidence"),
        "shot_ids": unique_shots,
        "shot_count": len(unique_shots),
        "episode_count": len({episode_by_shot[shot_id] for shot_id in unique_shots if shot_id in episode_by_shot}),
        "metadata": metadata,
    }


def _binding_intersection_suggestion(
    shot_ids: set[str],
    character_ids_by_shot: dict[str, set[str]],
) -> str | None:
    """只有所有观察 Shot 的 Final Character 交集唯一时才给建议。

    这不会把“同一镜里有两个人”误判成其中任意一个：如果共同出现的人物不唯一，返回 None，
    UI 必须继续人工定位。
    """

    if not shot_ids:
        return None
    sets = [character_ids_by_shot.get(shot_id, set()) for shot_id in shot_ids]
    if not sets or any(not values for values in sets):
        return None
    common = set.intersection(*sets)
    return next(iter(common)) if len(common) == 1 else None


def inventory(project_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with get_session() as session:
        episodes = list(session.scalars(
            select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order)
        ).all())
        if not episodes:
            return {
                "project_id": project_id,
                "revision": digest([None, [], []]),
                "observations": [],
                "characters": [],
                "summary": {
                    "character_count": 0,
                    "bound_shot_count": 0,
                    "observation_count": 0,
                    "confirmed_observation_count": 0,
                    "suggested_observation_count": 0,
                    "unresolved_observation_count": 0,
                },
            }

        episode_ids = [episode.id for episode in episodes]
        all_shots = list(session.scalars(select(Shot).where(Shot.episode_id.in_(episode_ids))).all())
        episode_by_shot = {shot.id: shot.episode_id for shot in all_shots}

        characters = list(session.scalars(
            select(Character).where(Character.project_id == project_id).order_by(Character.name)
        ).all())
        bindings = list(session.scalars(
            select(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id)
        ).all())

        bindings_by_character: dict[str, list[str]] = {}
        character_ids_by_shot: dict[str, set[str]] = {}
        for binding in bindings:
            bindings_by_character.setdefault(binding.character_id, []).append(binding.shot_id)
            character_ids_by_shot.setdefault(binding.shot_id, set()).add(binding.character_id)

        character_rows = [
            _character_payload(
                character,
                _json(character.metadata_json),
                bindings_by_character.get(character.id, []),
                episode_by_shot,
            )
            for character in characters
        ]
        revision = _current_revision(session, project_id)
        revision_id = revision.id if revision else None

        for episode in episodes:
            draft = get_current_breakdown(episode.id)
            if not draft:
                continue
            timeline = build_scene_timeline_result_v1(draft)
            if not timeline.get("is_current"):
                continue
            ids = {shot.ordinal: shot.id for shot in all_shots if shot.episode_id == episode.id}
            for row in observations(episode.id, timeline, ids):
                row["episode_title"] = episode.title
                row["character_id"] = None
                row["suggested_character_id"] = None
                row["suggestion_source"] = None

                row_shot_ids = {shot["id"] for shot in row["shots"]}
                matches = [
                    character
                    for character in character_rows
                    if any(
                        mapping.get("key") == row["key"] and mapping.get("anchor") == row["anchor"]
                        for mapping in character["metadata"].get(MAPPING_KEY, [])
                    )
                    and row_shot_ids <= set(character["shot_ids"])
                ]
                if len(matches) == 1:
                    matched = matches[0]
                    row["character_id"] = matched["id"]
                    mapping = next(
                        mapping
                        for mapping in matched["metadata"].get(MAPPING_KEY, [])
                        if mapping.get("key") == row["key"] and mapping.get("anchor") == row["anchor"]
                    )
                    mark = mapping.get("localization")
                    row["localization"] = (
                        mark
                        if isinstance(mark, dict)
                        and any(
                            shot["id"] == mark.get("shot_id")
                            and shot["thumbnail_url"] == mark.get("image_url")
                            for shot in row["shots"]
                        )
                        else None
                    )
                else:
                    suggestion = _binding_intersection_suggestion(row_shot_ids, character_ids_by_shot)
                    if suggestion:
                        row["suggested_character_id"] = suggestion
                        row["suggestion_source"] = "FINAL_SHOT_BINDING_INTERSECTION"
                rows.append(row)

    public_characters = [
        {key: value for key, value in character.items() if key != "metadata"}
        for character in character_rows
    ]
    confirmed = sum(1 for row in rows if row.get("character_id"))
    suggested = sum(1 for row in rows if not row.get("character_id") and row.get("suggested_character_id"))
    unresolved = len(rows) - confirmed - suggested
    return {
        "project_id": project_id,
        "revision": digest([revision_id, rows, character_rows]),
        "observations": rows,
        "characters": public_characters,
        "summary": {
            "character_count": len(public_characters),
            "bound_shot_count": len({binding.shot_id for binding in bindings}),
            "observation_count": len(rows),
            "confirmed_observation_count": confirmed,
            "suggested_observation_count": suggested,
            "unresolved_observation_count": unresolved,
        },
    }


def _valid_localization(row: dict[str, Any], mark: Any) -> bool:
    if not isinstance(mark, dict):
        return False
    shot = next((shot for shot in row["shots"] if shot["id"] == mark.get("shot_id")), None)
    box = mark.get("box", [])
    return bool(
        shot
        and shot["thumbnail_url"]
        and mark.get("image_url") == shot["thumbnail_url"]
        and isinstance(box, list)
        and len(box) == 4
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in box
        )
        and min(box) >= 0
        and box[2] >= 0.02
        and box[3] >= 0.02
        and box[0] + box[2] <= 1.000001
        and box[1] + box[3] <= 1.000001
    )


def assign(
    project_id: str,
    keys: list[str],
    name: str,
    character_id: str | None,
    expected_revision: str,
    localizations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """显式把若干人物观察归并到一个 Final Character。

    已有 Final Shot Binding 唯一指向目标人物时，不再要求重复手工框选；
    其余情况仍必须标记具体人物，防止同框人物误归并。
    """

    with LOCK:
        current = inventory(project_id)
        if current["revision"] != expected_revision:
            raise ValueError("人物或镜头已更新，请刷新后重新确认")
        key_set = set(keys)
        chosen = [row for row in current["observations"] if row["key"] in key_set]
        if not chosen or len(chosen) != len(key_set) or any(not row["shots"] for row in chosen):
            raise ValueError("请选择当前有镜头证据的人物")

        submitted_marks = localizations or {}
        normalized_localizations: dict[str, dict[str, Any] | None] = {}
        for row in chosen:
            mark = submitted_marks.get(row["key"])
            if _valid_localization(row, mark):
                normalized_localizations[row["key"]] = mark
                continue
            if character_id and row.get("suggested_character_id") == character_id:
                normalized_localizations[row["key"]] = row.get("localization")
                continue
            raise ValueError("该人物在当前镜头中无法唯一确定，请先框选具体人物再归并")

        existing = [
            row
            for row in current["observations"]
            if row["character_id"] == character_id and row["key"] not in key_set
        ] if character_id else []
        seen: set[str] = set()
        for row in chosen + existing:
            ids = {shot["id"] for shot in row["shots"]}
            if seen & ids:
                raise ValueError("同一镜头中的不同人物不能合并；请先修正重复的人物观察证据")
            seen.update(ids)

        with get_session() as session:
            target = session.get(Character, character_id) if character_id else None
            if character_id and (target is None or target.project_id != project_id):
                raise ValueError("目标原片人物不属于当前项目")
            if target is None:
                if not name.strip():
                    raise ValueError("请输入原片人物名称")
                target = Character(
                    id=new_id("CHAR"),
                    project_id=project_id,
                    name=name.strip(),
                    status="MANUAL",
                    metadata_json="{}",
                )
                session.add(target)
                session.flush()

            all_characters = list(session.scalars(
                select(Character).where(Character.project_id == project_id)
            ).all())
            # Reassignment only removes bindings created by this mapping workflow.
            for character in all_characters:
                meta = _json(character.metadata_json)
                old = list(meta.get(MAPPING_KEY) or [])
                kept = [mapping for mapping in old if mapping.get("key") not in key_set]
                removed_shots = {
                    shot_id
                    for mapping in old
                    if mapping.get("key") in key_set
                    for shot_id in mapping.get("shot_ids", [])
                }
                remaining_shots = {
                    shot_id
                    for mapping in kept
                    for shot_id in mapping.get("shot_ids", [])
                }
                for binding in session.scalars(
                    select(ShotCharacterBinding).where(ShotCharacterBinding.character_id == character.id)
                ).all():
                    if binding.source == "MANUAL_PERSON" and binding.shot_id in removed_shots - remaining_shots:
                        session.delete(binding)
                meta[MAPPING_KEY] = kept
                character.metadata_json = json.dumps(meta, ensure_ascii=False)
            session.flush()

            meta = _json(target.metadata_json)
            mappings = list(meta.get(MAPPING_KEY) or [])
            mappings.extend([
                {
                    "key": row["key"],
                    "anchor": row["anchor"],
                    "shot_ids": [shot["id"] for shot in row["shots"]],
                    "localization": normalized_localizations.get(row["key"]),
                }
                for row in chosen
            ])
            meta[MAPPING_KEY] = mappings
            meta["status"] = "MANUAL"
            target.metadata_json = json.dumps(meta, ensure_ascii=False)
            target.status = "MANUAL"

            bound = set(session.scalars(
                select(ShotCharacterBinding.shot_id).where(ShotCharacterBinding.character_id == target.id)
            ).all())
            for shot_id in {shot["id"] for row in chosen for shot in row["shots"]} - bound:
                session.add(ShotCharacterBinding(
                    id=new_id("SHOTCHAR"),
                    project_id=project_id,
                    shot_id=shot_id,
                    character_id=target.id,
                    source="MANUAL_PERSON",
                ))
            _manual_revision(session, project_id, f"确认并归并 {len(chosen)} 组原片人物：{target.name}")
            session.commit()
        return inventory(project_id)


def apply_person_mapping(episode_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """人工人物映射是独立权威，不通过放宽 AI 阈值来伪造自动识别。"""

    if not result or not result["timeline"].get("is_current"):
        return result
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if not episode:
            return result
        ids = {
            shot.ordinal: shot.id
            for shot in session.scalars(select(Shot).where(Shot.episode_id == episode_id)).all()
        }
        rows = observations(episode_id, result["timeline"], ids)
        characters = list(session.scalars(
            select(Character).where(Character.project_id == episode.project_id)
        ).all())
        revision = _current_revision(session, episode.project_id)
        changed = False
        for scene in result["identity"]["scenes"]:
            for person in scene["people"]:
                row = next((
                    item
                    for item in rows
                    if item["scene_ordinal"] == scene["scene_ordinal"] and item["ref"] == person["ref"]
                ), None)
                if not row:
                    continue
                matches: list[dict[str, Any]] = []
                for character in characters:
                    meta = _json(character.metadata_json)
                    if any(
                        mapping.get("key") == row["key"] and mapping.get("anchor") == row["anchor"]
                        for mapping in meta.get(MAPPING_KEY, [])
                    ):
                        bound = set(session.scalars(
                            select(ShotCharacterBinding.shot_id).where(
                                ShotCharacterBinding.character_id == character.id
                            )
                        ).all())
                        if {shot["id"] for shot in row["shots"]} <= bound:
                            matches.append({
                                "id": character.id,
                                "name": character.name,
                                "cover_url": meta.get("cover_url"),
                            })
                if len(matches) == 1:
                    person["character"] = matches[0]
                    person["display_name"] = matches[0]["name"]
                    changed = True
        if changed:
            overlay = result["identity"]
            people = [person for scene in overlay["scenes"] for person in scene["people"]]
            overlay["asset_revision_id"] = revision.id if revision else None
            overlay["resolved_count"] = sum(person["character"] is not None for person in people)
            overlay["unresolved_count"] = len(people) - overlay["resolved_count"]
            overlay["warnings"] = ["仍有原片人物待确认"] if overlay["unresolved_count"] else []
    return result
