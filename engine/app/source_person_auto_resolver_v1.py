"""Character V10.1 -> LocalSubject -> FinalCharacter 自动解析。

本模块只消费已经落库的不可变人物 Evidence，不在读路径重新运行视觉模型：
- CharacterTrack 表达某个 V10.1 Candidate 在 Shot 中的真实人物 Track；
- Character.metadata.source_candidate_ids 表达 FinalCharacter 来自哪些 Candidate；
- Breakdown LocalSubject 只提供 Scene 内局部人物及其出现 Shot 集合。

安全规则：
1. LocalSubject 的全部出现 Shot 都必须有 CharacterTrack Evidence；
2. 这些 Shot 的 Candidate 交集必须恰好只有一个 Candidate；
3. 该 Candidate 必须只映射到一个当前 FinalCharacter；
4. FinalCharacter 当前 Shot Binding 必须覆盖 LocalSubject 的全部出现 Shot；
5. 如果两个 LocalSubject 在重叠 Shot 中被解析成同一个 Candidate，则双方都降级 REVIEW，绝不自动写入。

满足以上硬条件时才标记 AUTO。其余情况只返回定位/诊断 Evidence，不猜身份。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from engine.app.asset_workspace_v3 import (
    ShotCharacterBinding,
    _create_revision,
    _current_revision,
)
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun
from engine.app.studio_v2 import Character, Shot, get_session

MAPPING_KEY = "source_person_mappings_v1"
AUTO_SOURCE = "CHARACTER_V10_1_EXACT_CANDIDATE"


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _video_dimensions(path: str | None) -> tuple[int, int] | None:
    """读取 V10.1 实际分析的 Reference Clip 尺寸，避免拿缩略图尺寸归一化 bbox。"""

    if not path or not Path(path).is_file():
        return None
    try:
        import cv2

        capture = cv2.VideoCapture(path)
        try:
            width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
            height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        finally:
            capture.release()
    except Exception:
        return None
    return (width, height) if width > 0 and height > 0 else None


def _image_dimensions(path: str | None) -> tuple[int, int] | None:
    if not path or not Path(path).is_file():
        return None
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return None
    return (int(width), int(height)) if width > 0 and height > 0 else None


def _shot_dimensions(shot: Shot, cache: dict[str, tuple[int, int] | None]) -> tuple[int, int] | None:
    if shot.id in cache:
        return cache[shot.id]
    dimensions = _video_dimensions(shot.reference_clip_path)
    if dimensions is None:
        dimensions = _image_dimensions(shot.thumbnail_path)
    cache[shot.id] = dimensions
    return dimensions


def _normalized_localization(
    track: CharacterTrack,
    shot: Shot,
    image_url: str | None,
    dimension_cache: dict[str, tuple[int, int] | None],
) -> dict[str, Any] | None:
    raw = _bbox(track.bbox_json)
    dimensions = _shot_dimensions(shot, dimension_cache)
    if raw is None or dimensions is None or not image_url:
        return None
    frame_width, frame_height = dimensions
    x, y, width, height = raw
    left = max(0.0, min(1.0, x / frame_width))
    top = max(0.0, min(1.0, y / frame_height))
    right = max(left, min(1.0, (x + width) / frame_width))
    bottom = max(top, min(1.0, (y + height) / frame_height))
    normalized_width = right - left
    normalized_height = bottom - top
    if normalized_width < 0.01 or normalized_height < 0.01:
        return None
    return {
        "shot_id": shot.id,
        "image_url": image_url,
        "box": [left, top, normalized_width, normalized_height],
        "source": AUTO_SOURCE,
        "track_id": track.id,
        "candidate_id": track.candidate_id,
    }


def _best_track(rows: list[CharacterTrack]) -> CharacterTrack | None:
    if not rows:
        return None
    return max(
        rows,
        key=lambda track: (
            1 if track.face_visible else 0,
            float(track.mean_face_score or 0.0),
            float(track.body_evidence_score or 0.0),
            int(track.sample_count or 0),
        ),
    )


def build_auto_resolution_plan(project_id: str, observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """为当前未确认 LocalSubject 生成只读自动解析计划。"""

    if not observations:
        return {}

    with get_session() as session:
        run = session.scalar(
            select(ContentAnalysisRun)
            .where(ContentAnalysisRun.project_id == project_id, ContentAnalysisRun.is_current.is_(True))
            .order_by(ContentAnalysisRun.completed_at.desc())
        )
        if run is None:
            return {}

        tracks = list(session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run.id)).all())
        if not tracks:
            return {}

        candidates = {
            item.id: item
            for item in session.scalars(select(CharacterCandidate).where(CharacterCandidate.run_id == run.id)).all()
        }
        characters = list(session.scalars(select(Character).where(Character.project_id == project_id)).all())
        bindings = list(session.scalars(
            select(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id)
        ).all())

        candidate_ids_by_shot: dict[str, set[str]] = {}
        tracks_by_candidate_shot: dict[tuple[str, str], list[CharacterTrack]] = {}
        for track in tracks:
            candidate_ids_by_shot.setdefault(track.shot_id, set()).add(track.candidate_id)
            tracks_by_candidate_shot.setdefault((track.candidate_id, track.shot_id), []).append(track)

        character_ids_by_candidate: dict[str, set[str]] = {}
        for character in characters:
            metadata = _json_object(character.metadata_json)
            for candidate_id in metadata.get("source_candidate_ids") or []:
                if isinstance(candidate_id, str) and candidate_id:
                    character_ids_by_candidate.setdefault(candidate_id, set()).add(character.id)

        bound_shots_by_character: dict[str, set[str]] = {}
        for binding in bindings:
            bound_shots_by_character.setdefault(binding.character_id, set()).add(binding.shot_id)

        shot_ids = {
            str(shot.get("id") or "")
            for observation in observations
            for shot in observation.get("shots") or []
            if shot.get("id")
        }
        shots = {
            shot.id: shot
            for shot in session.scalars(select(Shot).where(Shot.id.in_(shot_ids))).all()
        } if shot_ids else {}
        dimension_cache: dict[str, tuple[int, int] | None] = {}

        proposals: dict[str, dict[str, Any]] = {}
        for observation in observations:
            if observation.get("character_id") or observation.get("identity_issue"):
                continue
            observation_shots = list(observation.get("shots") or [])
            row_shot_ids = {str(item.get("id") or "") for item in observation_shots if item.get("id")}
            if not row_shot_ids:
                continue

            candidate_sets = [candidate_ids_by_shot.get(shot_id, set()) for shot_id in row_shot_ids]
            if not candidate_sets or any(not values for values in candidate_sets):
                continue
            common_candidates = set.intersection(*candidate_sets)
            if len(common_candidates) != 1:
                continue
            candidate_id = next(iter(common_candidates))
            candidate = candidates.get(candidate_id)

            mapped_characters = character_ids_by_candidate.get(candidate_id, set())
            character_id = next(iter(mapped_characters)) if len(mapped_characters) == 1 else None
            fully_bound = bool(
                character_id
                and row_shot_ids <= bound_shots_by_character.get(character_id, set())
            )

            localizations: list[dict[str, Any]] = []
            for item in observation_shots:
                shot_id = str(item.get("id") or "")
                shot = shots.get(shot_id)
                track = _best_track(tracks_by_candidate_shot.get((candidate_id, shot_id), []))
                if shot is None or track is None:
                    continue
                localization = _normalized_localization(
                    track,
                    shot,
                    str(item.get("thumbnail_url") or "") or None,
                    dimension_cache,
                )
                if localization is not None:
                    localizations.append(localization)

            proposals[str(observation["key"])] = {
                "decision": "AUTO" if character_id and fully_bound else "REVIEW",
                "source": AUTO_SOURCE,
                "source_run_id": run.id,
                "candidate_id": candidate_id,
                "candidate_confidence": candidate.confidence if candidate is not None else None,
                "character_id": character_id if fully_bound else None,
                "shot_ids": sorted(row_shot_ids),
                "localizations": localizations,
                "localization": localizations[0] if localizations else None,
                "reason": (
                    "V10.1 Candidate 在全部 LocalSubject Shot 中唯一，且对应唯一 FinalCharacter"
                    if character_id and fully_bound
                    else "已唯一定位 V10.1 Candidate，但 FinalCharacter 映射或当前 Shot Binding 不满足自动写入条件"
                ),
            }

    resolved_by_character: dict[str, list[set[str]]] = {}
    for observation in observations:
        character_id = str(observation.get("character_id") or "")
        if not character_id:
            continue
        resolved_by_character.setdefault(character_id, []).append({
            str(item.get("id") or "")
            for item in observation.get("shots") or []
            if item.get("id")
        })
    for proposal in proposals.values():
        character_id = str(proposal.get("character_id") or "")
        if proposal["decision"] != "AUTO" or not character_id:
            continue
        if any(set(proposal["shot_ids"]) & used for used in resolved_by_character.get(character_id, [])):
            proposal["decision"] = "REVIEW"
            proposal["character_id"] = None
            proposal["reason"] = "目标 FinalCharacter 已有另一个 LocalSubject 占用重叠 Shot，需要人工区分"

    keys = list(proposals)
    for index, left_key in enumerate(keys):
        left = proposals[left_key]
        if left["decision"] != "AUTO":
            continue
        for right_key in keys[index + 1:]:
            right = proposals[right_key]
            if right["decision"] != "AUTO":
                continue
            if left["candidate_id"] != right["candidate_id"]:
                continue
            if set(left["shot_ids"]) & set(right["shot_ids"]):
                left["decision"] = "REVIEW"
                right["decision"] = "REVIEW"
                left["character_id"] = None
                right["character_id"] = None
                left["reason"] = "同一 V10.1 Candidate 同时命中重叠 Shot 的多个 LocalSubject，需要人工区分"
                right["reason"] = left["reason"]

    return proposals


def persist_auto_resolutions(
    project_id: str,
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """持久化当前计划中所有 AUTO LocalSubject 映射；无安全结果时完全不写库。"""

    plan = build_auto_resolution_plan(project_id, observations)
    auto_rows = {
        key: proposal
        for key, proposal in plan.items()
        if proposal.get("decision") == "AUTO" and proposal.get("character_id")
    }
    if not auto_rows:
        return {"changed": False, "auto_bound_count": 0, "plan": plan}

    observations_by_key = {str(row.get("key") or ""): row for row in observations}
    with get_session() as session:
        current_revision = _current_revision(session, project_id)
        current_run = session.scalar(
            select(ContentAnalysisRun)
            .where(ContentAnalysisRun.project_id == project_id, ContentAnalysisRun.is_current.is_(True))
            .order_by(ContentAnalysisRun.completed_at.desc())
        )
        characters = {
            character.id: character
            for character in session.scalars(select(Character).where(Character.project_id == project_id)).all()
        }

        changed = 0
        for key, proposal in auto_rows.items():
            row = observations_by_key.get(key)
            target = characters.get(str(proposal["character_id"]))
            if row is None or target is None:
                continue
            metadata = _json_object(target.metadata_json)
            mappings = list(metadata.get(MAPPING_KEY) or [])
            if any(
                isinstance(mapping, dict)
                and mapping.get("key") == key
                and mapping.get("anchor") == row.get("anchor")
                for mapping in mappings
            ):
                continue
            mappings.append({
                "key": key,
                "anchor": row.get("anchor"),
                "shot_ids": list(proposal.get("shot_ids") or []),
                "localization": proposal.get("localization"),
                "decision_source": AUTO_SOURCE,
                "source_run_id": proposal.get("source_run_id"),
                "source_candidate_id": proposal.get("candidate_id"),
            })
            metadata[MAPPING_KEY] = mappings
            target.metadata_json = json.dumps(metadata, ensure_ascii=False)
            changed += 1

        if not changed:
            return {"changed": False, "auto_bound_count": 0, "plan": plan}

        revision_kind = current_revision.kind if current_revision is not None else "AUTO"
        _create_revision(
            session,
            project_id=project_id,
            kind=revision_kind,
            note=f"Character V10.1 自动确认 {changed} 组原片人物",
            source_run_id=current_run.id if current_run is not None else None,
            source_revision_id=current_revision.id if current_revision is not None else None,
        )
        session.commit()

    return {"changed": True, "auto_bound_count": changed, "plan": plan}


__all__ = [
    "AUTO_SOURCE",
    "MAPPING_KEY",
    "build_auto_resolution_plan",
    "persist_auto_resolutions",
]
