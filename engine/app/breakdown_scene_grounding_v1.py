"""G2.3：从冻结 ``scene-timeline-v1`` 构建 Scene-level 纯文本 Grounding Packet。

Grounding Packet 是 LLM 唯一允许读取的业务输入。它不重新读取 G1 Draft / Evidence，更不看视频。
每个可引用事实分配稳定的 Fxxxx id，并计算 source_fingerprint，后续 G2.4 用它防止 Narrative
overlay 被错误套到另一版 Timeline / Scene 上。

特别保护：ASR dialogue 与 OCR text 在 fact.text 中保持 Timeline 原字符串，不做 trim、纠错或替换。
"""
from __future__ import annotations

from hashlib import sha256
import json
from collections.abc import Mapping
from typing import Any

from engine.app.breakdown_scene_narrative_contract_v1 import (
    SCENE_GROUNDING_SCHEMA_VERSION,
    GroundingFactKindV1,
    SceneGroundingPacketV1,
)
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1


class SceneGroundingError(ValueError):
    """冻结 Timeline 无法安全构建指定 Scene Grounding Packet。"""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _verbatim(value: Any) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text if text.strip() else None


def _fact_people_from_text(text: str, display_to_ref: Mapping[str, str]) -> list[str]:
    refs: list[str] = []
    for display_name, ref in display_to_ref.items():
        if display_name in text and ref not in refs:
            refs.append(ref)
    return refs


def build_scene_grounding_packet_v1(
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
    scene_ordinal: int,
) -> dict[str, Any]:
    """只从 FINAL PASS Scene Timeline 为一个 Scene 建立纯文本 LLM grounding 输入。"""

    timeline = (
        timeline_payload
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload)
    )
    scene = next((item for item in timeline.scenes if item.ordinal == scene_ordinal), None)
    if scene is None:
        raise SceneGroundingError(f"Scene {scene_ordinal} 不存在")

    people = [item.model_dump(mode="json") for item in scene.people]
    display_to_ref = {item.display_name: item.ref for item in scene.people}
    facts: list[dict[str, Any]] = []

    def add_fact(
        kind: GroundingFactKindV1,
        text: str | None,
        *,
        shot_ordinal: int | None = None,
        people_refs: list[str] | None = None,
        verbatim: bool = False,
    ) -> None:
        if text is None:
            return
        value = _verbatim(text) if verbatim else " ".join(str(text).strip().split())
        if not value:
            return
        refs: list[str] = []
        for ref in people_refs or []:
            if ref and ref not in refs:
                refs.append(ref)
        for ref in _fact_people_from_text(value, display_to_ref):
            if ref not in refs:
                refs.append(ref)
        facts.append({
            "fact_id": f"F{len(facts) + 1:04d}",
            "kind": kind,
            "shot_ordinal": shot_ordinal,
            "people": refs,
            "text": value,
        })

    add_fact("SCENE_LOCATION", scene.scene_info.location)
    add_fact("SCENE_SPACE", scene.scene_info.interior_exterior)
    add_fact("SCENE_TIME", scene.scene_info.time_of_day)
    add_fact("SCENE_ENVIRONMENT", scene.scene_info.environment)
    add_fact("SCENE_BASE_SUMMARY", scene.story_summary)

    for person in scene.people:
        add_fact("PERSON_APPEARANCE", person.appearance, people_refs=[person.ref])

    for shot in scene.shots:
        add_fact("SHOT_VISUAL", shot.visual_description, shot_ordinal=shot.ordinal, people_refs=list(shot.people))
        for performance in shot.performance:
            add_fact(
                "SHOT_PERFORMANCE",
                performance.text,
                shot_ordinal=shot.ordinal,
                people_refs=list(performance.people),
            )
        for dialogue in shot.dialogue:
            add_fact(
                "DIALOGUE",
                dialogue.text,
                shot_ordinal=shot.ordinal,
                people_refs=list(dialogue.speakers),
                verbatim=True,
            )
        for prop in shot.props:
            add_fact("PROP", prop.label, shot_ordinal=shot.ordinal)
            add_fact("PROP_INTERACTION", prop.interaction, shot_ordinal=shot.ordinal)
        add_fact("SHOT_TYPE", shot.cinematography.shot_type, shot_ordinal=shot.ordinal)
        add_fact("COMPOSITION", shot.cinematography.composition, shot_ordinal=shot.ordinal)
        add_fact("CAMERA_MOTION", shot.cinematography.camera_motion, shot_ordinal=shot.ordinal)
        for ocr in shot.on_screen_text:
            add_fact("OCR", ocr.text, shot_ordinal=shot.ordinal, verbatim=True)

    # Fact id 必须连续唯一；任何未来修改导致重复/跳号都在这里 fail closed。
    expected_ids = [f"F{index:04d}" for index in range(1, len(facts) + 1)]
    actual_ids = [item["fact_id"] for item in facts]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(actual_ids):
        raise SceneGroundingError("Grounding fact id 不连续或重复")

    body = {
        "schema_version": SCENE_GROUNDING_SCHEMA_VERSION,
        "source_breakdown_run_id": timeline.source_breakdown_run_id,
        "source_shot_revision_id": timeline.source_shot_revision_id,
        "episode_id": timeline.episode_id,
        "scene_ordinal": scene.ordinal,
        "deterministic_title": scene.title,
        "scene_info": scene.scene_info.model_dump(mode="json"),
        "people": people,
        "facts": facts,
    }
    fingerprint = sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    payload = {**body, "source_fingerprint": fingerprint}
    validated = SceneGroundingPacketV1.model_validate(payload)
    return validated.model_dump(mode="json")


__all__ = ["SceneGroundingError", "build_scene_grounding_packet_v1"]
