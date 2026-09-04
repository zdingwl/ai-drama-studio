"""Revision-scoped manual overrides for ordinary-user Breakdown facts.

AI BreakdownRun / ShotSemanticDraft remain immutable evidence. User edits are stored as a
small versioned workspace artifact anchored to the current ShotRevision and are projected only
onto the current ordinary-user SceneTimeline/read-model surface.

No inference is executed here. A new ShotRevision automatically stops old overrides from
applying because the artifact path and payload anchor both include source_shot_revision_id.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any

from engine.app import studio_v2
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.breakdown_serializer_v1 import get_current_breakdown

MANUAL_OVERRIDE_SCHEMA_VERSION = "breakdown-manual-override-v1"
MANUAL_OVERRIDE_FILENAME = "manual-overrides-v1.json"

_SHOT_FIELDS = frozenset({
    "summary",
    "visual_description",
    "narrative_function",
    "performance_text",
    "expression",
    "posture",
    "gaze",
    "interaction",
    "shot_type",
    "camera_angle",
    "composition",
    "camera_motion",
    "lighting",
    "continuity",
})
_PERFORMANCE_DETAIL_FIELDS = frozenset({"expression", "posture", "gaze", "interaction"})
_CAMERA_FIELDS = frozenset({"shot_type", "camera_angle", "composition", "camera_motion", "lighting"})
_SCENE_FIELDS = frozenset({"location", "interior_exterior", "time_of_day", "environment"})
_WRITE_LOCK = RLock()


class BreakdownManualOverrideError(ValueError):
    """Manual override cannot be safely persisted or projected."""


def _draft_run(draft: Mapping[str, Any]) -> Mapping[str, Any]:
    run = draft.get("run")
    if not isinstance(run, Mapping):
        raise BreakdownManualOverrideError("当前拉片结果缺少 Run 锚点")
    return run


def _anchors(draft: Mapping[str, Any]) -> tuple[str, str, str]:
    run = _draft_run(draft)
    project_id = str(run.get("project_id") or "").strip()
    episode_id = str(run.get("episode_id") or "").strip()
    revision_id = str(run.get("source_shot_revision_id") or "").strip()
    if not project_id or not episode_id or not revision_id:
        raise BreakdownManualOverrideError("当前拉片结果缺少 Project / Episode / ShotRevision 锚点")
    return project_id, episode_id, revision_id


def manual_override_path_v1(draft: Mapping[str, Any]) -> Path:
    project_id, episode_id, revision_id = _anchors(draft)
    return (
        studio_v2.episode_dir(project_id, episode_id)
        / "breakdown"
        / "manual-overrides"
        / revision_id
        / MANUAL_OVERRIDE_FILENAME
    )


def _empty_artifact(draft: Mapping[str, Any]) -> dict[str, Any]:
    _, episode_id, revision_id = _anchors(draft)
    return {
        "schema_version": MANUAL_OVERRIDE_SCHEMA_VERSION,
        "episode_id": episode_id,
        "source_shot_revision_id": revision_id,
        "shots": {},
        "scenes": {},
        "dialogues": {},
    }


def _load_artifact(draft: Mapping[str, Any]) -> dict[str, Any]:
    path = manual_override_path_v1(draft)
    if not path.is_file():
        return _empty_artifact(draft)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BreakdownManualOverrideError("人工修改记录无法读取") from exc
    if not isinstance(raw, dict):
        raise BreakdownManualOverrideError("人工修改记录格式无效")
    _, episode_id, revision_id = _anchors(draft)
    if (
        raw.get("schema_version") != MANUAL_OVERRIDE_SCHEMA_VERSION
        or raw.get("episode_id") != episode_id
        or raw.get("source_shot_revision_id") != revision_id
    ):
        raise BreakdownManualOverrideError("人工修改记录与当前 ShotRevision 不一致")
    for key in ("shots", "scenes", "dialogues"):
        if not isinstance(raw.get(key), dict):
            raise BreakdownManualOverrideError("人工修改记录结构无效")
    return raw


def _persist_artifact(draft: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
    path = manual_override_path_v1(draft)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        serialized = json.dumps(dict(artifact), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise BreakdownManualOverrideError("人工修改内容无法安全保存") from exc
    temp = path.with_name(path.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _text_hash(value: Any) -> str:
    text = value if isinstance(value, str) else str(value or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scene_and_shot(timeline: Mapping[str, Any], shot_ordinal: int) -> tuple[dict[str, Any], dict[str, Any]]:
    for raw_scene in timeline.get("scenes") or []:
        if not isinstance(raw_scene, dict):
            continue
        for raw_shot in raw_scene.get("shots") or []:
            if isinstance(raw_shot, dict) and int(raw_shot.get("ordinal") or 0) == shot_ordinal:
                return raw_scene, raw_shot
    raise LookupError("当前分镜没有可编辑的拉片结果")


def persist_shot_manual_edit_v1(
    draft: Mapping[str, Any],
    base_timeline: Mapping[str, Any],
    *,
    shot_ordinal: int,
    edits: Mapping[str, Any],
) -> None:
    """Persist one explicit user edit without touching the immutable AI draft."""

    if _draft_run(draft).get("is_current") is not True:
        raise BreakdownManualOverrideError("只允许修改当前拉片结果")
    if shot_ordinal <= 0:
        raise BreakdownManualOverrideError("shot_ordinal 必须大于 0")
    scene, shot = _scene_and_shot(base_timeline, shot_ordinal)
    unknown = set(edits) - (_SHOT_FIELDS | {"scene", "dialogues"})
    if unknown:
        raise BreakdownManualOverrideError(f"不支持修改字段：{', '.join(sorted(unknown))}")

    with _WRITE_LOCK:
        artifact = _load_artifact(draft)
        shots = artifact["shots"]
        scenes = artifact["scenes"]
        dialogues = artifact["dialogues"]
        shot_key = str(shot_ordinal)

        shot_fields = {key: edits[key] for key in _SHOT_FIELDS if key in edits}
        if shot_fields:
            current = shots.get(shot_key)
            if not isinstance(current, dict):
                current = {
                    "start_us": int(shot["start_us"]),
                    "end_us": int(shot["end_us"]),
                    "fields": {},
                }
            if current.get("start_us") != int(shot["start_us"]) or current.get("end_us") != int(shot["end_us"]):
                current = {
                    "start_us": int(shot["start_us"]),
                    "end_us": int(shot["end_us"]),
                    "fields": {},
                }
            fields = current.get("fields") if isinstance(current.get("fields"), dict) else {}
            fields.update(shot_fields)
            current["fields"] = fields
            shots[shot_key] = current

        scene_edit = edits.get("scene")
        if scene_edit is not None:
            if not isinstance(scene_edit, Mapping):
                raise BreakdownManualOverrideError("scene 必须是对象")
            unknown_scene = set(scene_edit) - _SCENE_FIELDS
            if unknown_scene:
                raise BreakdownManualOverrideError(f"不支持修改场景字段：{', '.join(sorted(unknown_scene))}")
            scene_key = str(int(scene["ordinal"]))
            current_scene = scenes.get(scene_key)
            if not isinstance(current_scene, dict) or (
                current_scene.get("start_us") != int(scene["start_us"])
                or current_scene.get("end_us") != int(scene["end_us"])
            ):
                current_scene = {
                    "start_us": int(scene["start_us"]),
                    "end_us": int(scene["end_us"]),
                    "fields": {},
                }
            fields = current_scene.get("fields") if isinstance(current_scene.get("fields"), dict) else {}
            fields.update({key: scene_edit[key] for key in _SCENE_FIELDS if key in scene_edit})
            current_scene["fields"] = fields
            scenes[scene_key] = current_scene

        dialogue_edits = edits.get("dialogues")
        if dialogue_edits is not None:
            if not isinstance(dialogue_edits, list):
                raise BreakdownManualOverrideError("dialogues 必须是数组")
            base_dialogues = shot.get("dialogue") if isinstance(shot.get("dialogue"), list) else []
            shot_dialogues = dialogues.get(shot_key)
            if not isinstance(shot_dialogues, dict):
                shot_dialogues = {}
            for item in dialogue_edits:
                if not isinstance(item, Mapping):
                    raise BreakdownManualOverrideError("对白修改项必须是对象")
                try:
                    index = int(item.get("index"))
                except (TypeError, ValueError) as exc:
                    raise BreakdownManualOverrideError("对白 index 无效") from exc
                if index < 0 or index >= len(base_dialogues):
                    raise BreakdownManualOverrideError("对白 index 超出当前分镜范围")
                base_dialogue = base_dialogues[index]
                if not isinstance(base_dialogue, Mapping):
                    raise BreakdownManualOverrideError("当前对白数据无效")
                text = item.get("text")
                if not isinstance(text, str):
                    raise BreakdownManualOverrideError("对白文本必须是字符串")
                shot_dialogues[str(index)] = {
                    "start_us": int(base_dialogue["start_us"]),
                    "end_us": int(base_dialogue["end_us"]),
                    "source_text_sha256": _text_hash(base_dialogue.get("text")),
                    "text": text,
                }
            dialogues[shot_key] = shot_dialogues

        _persist_artifact(draft, artifact)


def _source_shot_map(
    source_timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1 | None,
) -> dict[int, Mapping[str, Any]]:
    if source_timeline_payload is None:
        return {}
    normalized = (
        source_timeline_payload.model_dump(mode="json")
        if isinstance(source_timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(source_timeline_payload).model_dump(mode="json")
    )
    result: dict[int, Mapping[str, Any]] = {}
    for scene in normalized["scenes"]:
        for shot in scene["shots"]:
            result[int(shot["ordinal"])] = shot
    return result


def apply_manual_overrides_v1(
    draft: Mapping[str, Any],
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
    *,
    source_timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1 | None = None,
) -> dict[str, Any]:
    """Project revision-compatible user edits onto the current SceneTimeline payload.

    When ``source_timeline_payload`` is supplied, dialogue authority is anchored to the immutable
    full-Run AI baseline while the effective (possibly single-Shot-rerun) dialogue must still retain
    the same index and exact time range.  This keeps an explicit user correction above later AI text
    without ever forcing it onto a structurally different dialogue segment.
    """

    timeline = (
        timeline_payload.model_dump(mode="json")
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload).model_dump(mode="json")
    )
    # Historical Run endpoints must remain immutable evidence. A manual correction is a current
    # source-fact overlay, not a rewrite of every Run that happens to share the same ShotRevision.
    if _draft_run(draft).get("is_current") is not True:
        return timeline

    source_shots = _source_shot_map(source_timeline_payload)
    artifact = _load_artifact(draft)
    if not artifact["shots"] and not artifact["scenes"] and not artifact["dialogues"]:
        return timeline

    for scene in timeline["scenes"]:
        scene_override = artifact["scenes"].get(str(scene["ordinal"]))
        if isinstance(scene_override, Mapping) and (
            scene_override.get("start_us") == scene["start_us"]
            and scene_override.get("end_us") == scene["end_us"]
        ):
            fields = scene_override.get("fields")
            if isinstance(fields, Mapping):
                info = dict(scene["scene_info"])
                for key in _SCENE_FIELDS:
                    if key in fields:
                        info[key] = fields[key]
                scene["scene_info"] = info

        for shot in scene["shots"]:
            shot_key = str(shot["ordinal"])
            shot_override = artifact["shots"].get(shot_key)
            if isinstance(shot_override, Mapping) and (
                shot_override.get("start_us") == shot["start_us"]
                and shot_override.get("end_us") == shot["end_us"]
            ):
                fields = shot_override.get("fields")
                if isinstance(fields, Mapping):
                    for key in ("summary", "visual_description", "narrative_function", "continuity"):
                        if key in fields:
                            shot[key] = fields[key]
                    if "performance_text" in fields:
                        text = fields["performance_text"]
                        shot["performance"] = [] if not text else [{"text": text, "people": list(shot["people"])}]
                    if any(key in fields for key in _PERFORMANCE_DETAIL_FIELDS):
                        details = dict(shot.get("performance_details") or {})
                        for key in _PERFORMANCE_DETAIL_FIELDS:
                            if key in fields:
                                details[key] = fields[key]
                        shot["performance_details"] = details
                    camera = dict(shot["cinematography"])
                    for key in _CAMERA_FIELDS:
                        if key in fields:
                            camera[key] = fields[key]
                    shot["cinematography"] = camera

            dialogue_overrides = artifact["dialogues"].get(shot_key)
            if isinstance(dialogue_overrides, Mapping):
                source_shot = source_shots.get(int(shot["ordinal"]), shot)
                source_dialogues = source_shot.get("dialogue") if isinstance(source_shot, Mapping) else []
                if not isinstance(source_dialogues, list):
                    source_dialogues = []
                for raw_index, override in dialogue_overrides.items():
                    if not isinstance(override, Mapping):
                        continue
                    try:
                        index = int(raw_index)
                    except (TypeError, ValueError):
                        continue
                    if index < 0 or index >= len(shot["dialogue"]) or index >= len(source_dialogues):
                        continue
                    dialogue = shot["dialogue"][index]
                    source_dialogue = source_dialogues[index]
                    if not isinstance(source_dialogue, Mapping):
                        continue
                    if (
                        override.get("start_us") != source_dialogue.get("start_us")
                        or override.get("end_us") != source_dialogue.get("end_us")
                        or override.get("source_text_sha256") != _text_hash(source_dialogue.get("text"))
                        or override.get("start_us") != dialogue["start_us"]
                        or override.get("end_us") != dialogue["end_us"]
                    ):
                        continue
                    text = override.get("text")
                    if isinstance(text, str):
                        dialogue["text"] = text

    return SceneTimelinePayloadV1.model_validate(timeline).model_dump(mode="json")


def apply_current_manual_overrides_to_read_model_v1(
    episode_id: str,
    read_model_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Apply current manual edits to the nested P6 Timeline while leaving asset/identity overlays intact."""

    if read_model_payload is None:
        return None
    draft = get_current_breakdown(episode_id)
    if draft is None:
        return dict(read_model_payload)
    result = dict(read_model_payload)
    timeline = result.get("timeline")
    if not isinstance(timeline, Mapping):
        raise BreakdownManualOverrideError("Breakdown read model 缺少 timeline")
    result["timeline"] = apply_manual_overrides_v1(draft, timeline)
    return result


__all__ = [
    "BreakdownManualOverrideError",
    "MANUAL_OVERRIDE_SCHEMA_VERSION",
    "apply_current_manual_overrides_to_read_model_v1",
    "apply_manual_overrides_v1",
    "manual_override_path_v1",
    "persist_shot_manual_edit_v1",
]
