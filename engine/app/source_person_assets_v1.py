"""原片人物归并：人工决定写正式人物、观察映射及 Shot Binding，AI 证据只读。"""
from __future__ import annotations

import hashlib
import json
import math
from threading import RLock
from sqlalchemy import select
from engine.app.studio_v2 import Character, Episode, Shot, get_session, new_id
from engine.app.asset_workspace_v3 import ShotCharacterBinding, _manual_revision, _current_revision
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.breakdown_scene_timeline_result_v1 import build_scene_timeline_result_v1

LOCK = RLock()
MAPPING_KEY = "source_person_mappings_v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def observations(episode_id, timeline, shot_ids):
    rows = []
    for scene in timeline["scenes"]:
        for person in scene["people"]:
            appearances = [s for s in scene["shots"] if person["ref"] in s["people"]]
            key = f'{episode_id}:{scene["ordinal"]}:{person["ref"]}'
            anchor = digest({"run": timeline["source_breakdown_run_id"], "revision": timeline["source_shot_revision_id"],
                             "person": person, "shots": [(s["ordinal"], s["start_us"], s["end_us"]) for s in appearances]})
            rows.append({"key": key, "anchor": anchor, "episode_id": episode_id, "scene_ordinal": scene["ordinal"],
                         "ref": person["ref"], "name": person["display_name"], "appearance": person.get("appearance"),
                         "scene": scene["title"], "shots": [{"id": shot_ids[s["ordinal"]], "ordinal": s["ordinal"],
                         "thumbnail_url": s.get("thumbnail_url")} for s in appearances if s["ordinal"] in shot_ids]})
    return rows


def inventory(project_id):
    rows = []
    with get_session() as session:
        episodes = session.scalars(select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order)).all()
        characters = session.scalars(select(Character).where(Character.project_id == project_id)).all()
        bindings = session.scalars(select(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id)).all()
        character_rows = [{"id": c.id, "name": c.name, "metadata": json.loads(c.metadata_json or "{}"),
                           "shot_ids": sorted(b.shot_id for b in bindings if b.character_id == c.id)} for c in characters]
        revision = _current_revision(session, project_id)
        revision_id = revision.id if revision else None
        for episode in episodes:
            draft = get_current_breakdown(episode.id)
            if not draft:
                continue
            timeline = build_scene_timeline_result_v1(draft)
            if not timeline.get("is_current"):
                continue
            ids = {s.ordinal: s.id for s in session.scalars(select(Shot).where(Shot.episode_id == episode.id)).all()}
            for row in observations(episode.id, timeline, ids):
                row["episode_title"] = episode.title
                row["character_id"] = None
                matches = [c for c in character_rows if any(m.get("key") == row["key"] and m.get("anchor") == row["anchor"]
                           for m in c["metadata"].get(MAPPING_KEY, [])) and {s["id"] for s in row["shots"]} <= set(c["shot_ids"])]
                if len(matches) == 1:
                    row["character_id"] = matches[0]["id"]
                    mapping = next(m for m in matches[0]["metadata"].get(MAPPING_KEY, []) if m.get("key") == row["key"] and m.get("anchor") == row["anchor"])
                    mark = mapping.get("localization")
                    row["localization"] = mark if isinstance(mark, dict) and any(s["id"] == mark.get("shot_id") and s["thumbnail_url"] == mark.get("image_url") for s in row["shots"]) else None
                rows.append(row)
    return {"project_id": project_id, "revision": digest([revision_id, rows, character_rows]),
            "observations": rows, "characters": [{k: v for k, v in c.items() if k != "metadata"} for c in character_rows]}


def assign(project_id, keys, name, character_id, expected_revision, localizations=None):
    with LOCK:
        current = inventory(project_id)
        if current["revision"] != expected_revision:
            raise ValueError("人物或镜头已更新，请刷新后重新确认")
        chosen = [r for r in current["observations"] if r["key"] in keys]
        if not chosen or len(chosen) != len(set(keys)) or any(not r["shots"] for r in chosen):
            raise ValueError("请选择当前有镜头证据的人物")
        if localizations is not None:
            for row in chosen:
                mark = localizations.get(row["key"], {})
                if not isinstance(mark, dict):
                    raise ValueError("请先标记要绑定的人物")
                shot = next((s for s in row["shots"] if s["id"] == mark.get("shot_id")), None)
                box = mark.get("box", [])
                if (not shot or not shot["thumbnail_url"] or mark.get("image_url") != shot["thumbnail_url"]
                        or not isinstance(box, list) or len(box) != 4 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in box)
                        or min(box) < 0 or box[2] < .02 or box[3] < .02 or box[0] + box[2] > 1.000001 or box[1] + box[3] > 1.000001):
                    raise ValueError("请先在当前镜头画面中标记要绑定的人物，再确认归并")
        existing = [r for r in current["observations"] if r["character_id"] == character_id and r["key"] not in keys] if character_id else []
        seen = set()
        for row in chosen + existing:
            ids = {s["id"] for s in row["shots"]}
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
                target = Character(id=new_id("CHAR"), project_id=project_id, name=name.strip(), status="MANUAL", metadata_json="{}")
                session.add(target)
                session.flush()
            all_characters = session.scalars(select(Character).where(Character.project_id == project_id)).all()
            # Reassignment removes only bindings owned by this mapping workflow.
            for character in all_characters:
                meta = json.loads(character.metadata_json or "{}")
                old = meta.get(MAPPING_KEY, [])
                kept = [m for m in old if m.get("key") not in keys]
                removed_shots = {sid for m in old if m.get("key") in keys for sid in m.get("shot_ids", [])}
                remaining_shots = {sid for m in kept for sid in m.get("shot_ids", [])}
                for binding in session.scalars(select(ShotCharacterBinding).where(ShotCharacterBinding.character_id == character.id)).all():
                    if binding.source == "MANUAL_PERSON" and binding.shot_id in removed_shots - remaining_shots:
                        session.delete(binding)
                meta[MAPPING_KEY] = kept
                character.metadata_json = json.dumps(meta, ensure_ascii=False)
            session.flush()
            meta = json.loads(target.metadata_json or "{}")
            meta[MAPPING_KEY] += [{"key": r["key"], "anchor": r["anchor"], "shot_ids": [s["id"] for s in r["shots"]],
                                  "localization": localizations[r["key"]] if localizations is not None else r.get("localization")} for r in chosen]
            target.metadata_json = json.dumps(meta, ensure_ascii=False)
            bound = set(session.scalars(select(ShotCharacterBinding.shot_id).where(ShotCharacterBinding.character_id == target.id)).all())
            for sid in {s["id"] for r in chosen for s in r["shots"]} - bound:
                session.add(ShotCharacterBinding(id=new_id("SHOTCHAR"), project_id=project_id, shot_id=sid, character_id=target.id, source="MANUAL_PERSON"))
            _manual_revision(session, project_id, f"确认并归并 {len(chosen)} 组原片人物：{target.name}")
            session.commit()
        return inventory(project_id)


def apply_person_mapping(episode_id, result):
    """Explicit human mappings are an independent authority, never an AI threshold relaxation."""
    if not result or not result["timeline"].get("is_current"):
        return result
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if not episode:
            return result
        ids = {s.ordinal: s.id for s in session.scalars(select(Shot).where(Shot.episode_id == episode_id)).all()}
        rows = observations(episode_id, result["timeline"], ids)
        chars = session.scalars(select(Character).where(Character.project_id == episode.project_id)).all()
        revision = _current_revision(session, episode.project_id)
        changed = False
        for scene in result["identity"]["scenes"]:
            for person in scene["people"]:
                row = next((r for r in rows if r["scene_ordinal"] == scene["scene_ordinal"] and r["ref"] == person["ref"]), None)
                if not row:
                    continue
                matches = []
                for character in chars:
                    meta = json.loads(character.metadata_json or "{}")
                    if any(m.get("key") == row["key"] and m.get("anchor") == row["anchor"] for m in meta.get(MAPPING_KEY, [])):
                        bound = set(session.scalars(select(ShotCharacterBinding.shot_id).where(ShotCharacterBinding.character_id == character.id)).all())
                        if {s["id"] for s in row["shots"]} <= bound:
                            matches.append({"id": character.id, "name": character.name, "cover_url": meta.get("cover_url")})
                if len(matches) == 1:
                    person["character"] = matches[0]
                    person["display_name"] = matches[0]["name"]
                    changed = True
        if changed:
            overlay = result["identity"]
            people = [p for s in overlay["scenes"] for p in s["people"]]
            overlay["asset_revision_id"] = revision.id if revision else None
            overlay["resolved_count"] = sum(p["character"] is not None for p in people)
            overlay["unresolved_count"] = len(people) - overlay["resolved_count"]
            overlay["warnings"] = ["仍有原片人物待确认"] if overlay["unresolved_count"] else []
    return result
