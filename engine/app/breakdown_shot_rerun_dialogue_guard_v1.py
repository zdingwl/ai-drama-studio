"""Fail-closed dialogue guard for scoped Shot reruns.

One ASR utterance can be projected across multiple Shots.  Historical full-run Fusion may copy the
same complete segment text into every intersecting Shot when word timestamps are unavailable;
SourceDramaSnapshot later recognizes those equal projections as one utterance.  Replacing only one
projection with a newly transcribed string would make the downstream canonical utterance concatenate
incompatible pieces.

Therefore a scoped Shot rerun never changes a Shot's dialogue list when that Shot contains any
``dialogue_group_id`` that also appears in another Shot.  Users can still correct the text explicitly
(manual corrections are applied after this guard), or run a complete Episode breakdown so all
projections are regenerated together.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1


CROSS_SHOT_DIALOGUE_GUARD_WARNING = (
    "部分对白跨越多个分镜；为避免单镜重拉破坏完整对白分组，已保留整集对白基线。"
    "需要修改时请人工校正该对白，或执行整集拉片。"
)


def _normalize(
    value: Mapping[str, Any] | SceneTimelinePayloadV1,
) -> dict[str, Any]:
    return (
        value.model_dump(mode="json")
        if isinstance(value, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(value).model_dump(mode="json")
    )


def _shots(payload: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for scene in payload.get("scenes") or []:
        if not isinstance(scene, Mapping):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, Mapping):
                continue
            try:
                result[int(shot.get("ordinal"))] = shot
            except (TypeError, ValueError):
                continue
    return result


def guard_cross_shot_dialogue_rerun_v1(
    source_timeline: Mapping[str, Any] | SceneTimelinePayloadV1,
    effective_timeline: Mapping[str, Any] | SceneTimelinePayloadV1,
) -> dict[str, Any]:
    """Restore full-run dialogue for Shots containing a cross-Shot dialogue group if AI changed it."""

    source = _normalize(source_timeline)
    effective = _normalize(effective_timeline)
    source_shots = _shots(source)

    counts: Counter[str] = Counter()
    guarded_shots: set[int] = set()
    for ordinal, shot in source_shots.items():
        dialogue = shot.get("dialogue")
        if not isinstance(dialogue, list):
            continue
        for item in dialogue:
            if not isinstance(item, Mapping):
                continue
            group_id = str(item.get("dialogue_group_id") or "").strip()
            if group_id:
                counts[group_id] += 1

    for ordinal, shot in source_shots.items():
        dialogue = shot.get("dialogue")
        if not isinstance(dialogue, list):
            continue
        if any(
            isinstance(item, Mapping)
            and counts[str(item.get("dialogue_group_id") or "").strip()] > 1
            for item in dialogue
            if str(item.get("dialogue_group_id") or "").strip()
        ):
            guarded_shots.add(ordinal)

    changed = False
    for scene in effective["scenes"]:
        for shot in scene["shots"]:
            ordinal = int(shot["ordinal"])
            if ordinal not in guarded_shots:
                continue
            source_shot = source_shots.get(ordinal)
            if source_shot is None:
                continue
            source_dialogue = source_shot.get("dialogue")
            if not isinstance(source_dialogue, list):
                continue
            if shot.get("dialogue") != source_dialogue:
                shot["dialogue"] = deepcopy(source_dialogue)
                changed = True

    if changed:
        warnings = [str(item) for item in effective.get("warnings") or []]
        if CROSS_SHOT_DIALOGUE_GUARD_WARNING not in warnings:
            warnings.append(CROSS_SHOT_DIALOGUE_GUARD_WARNING)
        effective["warnings"] = warnings

    return SceneTimelinePayloadV1.model_validate(effective).model_dump(mode="json")


__all__ = [
    "CROSS_SHOT_DIALOGUE_GUARD_WARNING",
    "guard_cross_shot_dialogue_rerun_v1",
]
