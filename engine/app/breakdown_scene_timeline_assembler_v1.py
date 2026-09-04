"""G2.2：把已冻结 G1 Breakdown Draft 确定性整理成 Scene Timeline。

输入是 ``breakdown_serializer_v1`` 已经提供的只读 Draft payload；本模块：
- 不读视频、不运行 ASR/OCR/VLM/LLM；
- 不修改 SceneSegmentDraft / ShotSemanticDraft / LocalSubject / DraftPropHint；
- Exact-Shot ``visual_description`` 优先作为当前 Shot 可见事实；
- 只接受 ``origin=ASR`` 的 DIALOGUE 作为对白文本，且原文逐字保留；
- 同一个 ASR segment 跨 Shot 时生成同一个 run-scoped ``dialogue_group_id``，不再把 TimelineEvent.id 当完整对白身份；
- 只接受 ``origin=OCR`` 的 OCR event 作为画面文字，且原文逐字保留；
- LocalSubject 仅映射为当前 Scene 内的 P1/P2/... + 人物1/人物2/...；
- 不创建 Character / Final Scene / Final Prop，也不读取 Final Asset 绑定；
- Evidence、cluster、confidence、provider metadata 等技术字段不会进入输出。

G2.2 的目标是先建立一个“没有 LLM 也能直接看”的稳定结果底座。后续 Scene-level
纯文本 LLM 只能在此结果之上增加受验证的可读整理，不能反向改写这些事实。
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import hashlib
from typing import Any

from engine.app.breakdown_scene_timeline_contract_v1 import (
    SCENE_TIMELINE_SCHEMA_VERSION,
    SceneTimelinePayloadV1,
)


class SceneTimelineAssemblyError(ValueError):
    """G1 Draft 无法安全映射为 Scene Timeline 时 fail closed。"""


_SPACE_LABELS = {
    "INTERIOR": "室内",
    "INT": "室内",
    "EXTERIOR": "室外",
    "EXT": "室外",
    "MIXED": "室内/室外",
}
_TIME_LABELS = {
    "DAY": "白天",
    "NIGHT": "夜晚",
    "DAWN": "黎明",
    "DUSK": "黄昏",
}
_SHOT_TYPE_LABELS = {
    "CLOSE_UP": "特写",
    "CLOSEUP": "特写",
    "EXTREME_CLOSE_UP": "大特写",
    "MEDIUM_CLOSE_UP": "近景",
    "MEDIUM": "中景",
    "MEDIUM_SHOT": "中景",
    "FULL": "全景",
    "FULL_SHOT": "全景",
    "WIDE": "全景",
    "WIDE_SHOT": "全景",
    "LONG": "远景",
    "LONG_SHOT": "远景",
}


def _records(value: Any) -> list[Mapping[str, Any]]:
    """只接受 JSON array 中的 object；坏元素不会被当作事实读取。"""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SceneTimelineAssemblyError(f"{label} 缺失")
    return text


def _clean_text(value: Any, *, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:limit] if text else None


def _unique_join(values: list[str | None], *, limit: int = 2000) -> str | None:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value, limit=limit)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    joined = "；".join(result)
    return joined[:limit] if joined else None


def _verbatim_text(value: Any) -> str | None:
    """对白/OCR 专用：只判断是否为空，不做 trim/空白归一化，避免改写源文本。"""

    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text if text.strip() else None


def _required_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise SceneTimelineAssemblyError(f"{label} 必须是整数")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SceneTimelineAssemblyError(f"{label} 必须是整数") from exc
    return number


def _range(owner: Mapping[str, Any], label: str) -> tuple[int, int]:
    start_us = _required_int(owner.get("source_start_us"), f"{label}.source_start_us")
    end_us = _required_int(owner.get("source_end_us"), f"{label}.source_end_us")
    if start_us < 0 or end_us < start_us:
        raise SceneTimelineAssemblyError(f"{label} 时间范围无效")
    return start_us, end_us


def _display_space(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return _SPACE_LABELS.get(normalized)


def _display_time(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return _TIME_LABELS.get(normalized)


def _display_shot_type(value: Any) -> str | None:
    text = _clean_text(value, limit=64)
    if not text:
        return None
    return _SHOT_TYPE_LABELS.get(text.upper(), text)


def _display_camera_motion(value: Any) -> str | None:
    text = _clean_text(value, limit=64)
    if not text or text.upper() == "UNKNOWN":
        return None
    return text


def _subject_id_from_relation(value: Mapping[str, Any]) -> str:
    direct = str(value.get("local_subject_id") or "").strip()
    if direct:
        return direct
    subject = value.get("subject")
    if isinstance(subject, Mapping):
        return str(subject.get("id") or "").strip()
    return ""


def _replace_local_labels(text: str | None, replacements: Mapping[str, str]) -> str | None:
    """仅整理匿名展示标签；对白/OCR 永远不会调用本函数。"""

    if not text:
        return text
    result = text
    for source in sorted(replacements, key=len, reverse=True):
        result = result.replace(source, replacements[source])
    return result


def _person_context(
    segment: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """建立当前 Scene 独立的 P1/P2/... 空间，绝不跨 Scene 复用 LocalSubject identity。"""

    subjects = _records(segment.get("subjects"))
    subjects.sort(key=lambda item: _required_int(item.get("ordinal"), "LocalSubject.ordinal"))

    subject_ids: set[str] = set()
    ordinals: set[int] = set()
    label_counts = Counter(str(item.get("display_label") or "").strip() for item in subjects)
    people: list[dict[str, Any]] = []
    ref_by_subject_id: dict[str, str] = {}
    label_replacements: dict[str, str] = {}

    for index, subject in enumerate(subjects, start=1):
        subject_id = _required_text(subject.get("id"), "LocalSubject.id")
        ordinal = _required_int(subject.get("ordinal"), "LocalSubject.ordinal")
        if subject_id in subject_ids:
            raise SceneTimelineAssemblyError("同一 Scene 出现重复 LocalSubject.id")
        if ordinal in ordinals:
            raise SceneTimelineAssemblyError("同一 Scene 出现重复 LocalSubject.ordinal")
        subject_ids.add(subject_id)
        ordinals.add(ordinal)

        ref = f"P{index}"
        display_name = f"人物{index}"
        ref_by_subject_id[subject_id] = ref
        people.append({
            "ref": ref,
            "display_name": display_name,
            "appearance": _clean_text(subject.get("appearance_summary"), limit=1000),
        })

        source_label = str(subject.get("display_label") or "").strip()
        if source_label and label_counts[source_label] == 1:
            label_replacements[source_label] = display_name

    return people, ref_by_subject_id, label_replacements


def _event_refs(
    event: Mapping[str, Any],
    ref_by_subject_id: Mapping[str, str],
    *,
    roles: set[str] | None = None,
) -> list[str]:
    refs: list[str] = []
    for participant in _records(event.get("participants")):
        role = str(participant.get("role") or "").strip().upper()
        if roles is not None and role not in roles:
            continue
        subject_id = _subject_id_from_relation(participant)
        ref = ref_by_subject_id.get(subject_id)
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _event_sort_key(event: Mapping[str, Any]) -> tuple[int, int, str]:
    try:
        start_us = int(event.get("source_start_us") or 0)
    except (TypeError, ValueError):
        start_us = 0
    try:
        ordinal = int(event.get("ordinal") or 0)
    except (TypeError, ValueError):
        ordinal = 0
    return start_us, ordinal, str(event.get("id") or "")


def _dialogue_group_id(run_id: str, event: Mapping[str, Any]) -> str:
    """给完整 ASR utterance 生成当前 BreakdownRun 内稳定的业务身份。"""

    metadata = event.get("metadata")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    explicit = str(metadata_map.get("dialogue_group_id") or "").strip()
    if explicit:
        return explicit
    asr_segment_id = str(metadata_map.get("asr_segment_id") or "").strip()
    event_id = str(event.get("id") or "").strip()
    anchor = asr_segment_id or event_id
    if not anchor:
        raise SceneTimelineAssemblyError("ASR DIALOGUE 缺少可构造 dialogue_group_id 的来源锚点")
    digest = hashlib.sha256(f"{run_id}\0{anchor}".encode("utf-8")).hexdigest()[:24]
    return f"{run_id}:DG:{digest}"


def _shot_people_and_performance(
    shot: Mapping[str, Any],
    ref_by_subject_id: Mapping[str, str],
    label_replacements: Mapping[str, str],
) -> tuple[list[str], list[dict[str, Any]]]:
    people: list[str] = []
    performance: list[dict[str, Any]] = []
    seen_performance: set[tuple[str, tuple[str, ...]]] = set()

    for presence in _records(shot.get("subjects")):
        subject_id = _subject_id_from_relation(presence)
        ref = ref_by_subject_id.get(subject_id)
        if not ref:
            continue
        if ref not in people:
            people.append(ref)
        activity = _clean_text(presence.get("activity_summary"), limit=1200)
        activity = _replace_local_labels(activity, label_replacements)
        if activity:
            key = (activity, (ref,))
            if key not in seen_performance:
                seen_performance.add(key)
                performance.append({"text": activity, "people": [ref]})

    for event in sorted(_records(shot.get("events")), key=_event_sort_key):
        if str(event.get("event_type") or "").strip().upper() != "ACTION":
            continue
        text = _clean_text(event.get("content_text"), limit=1200)
        text = _replace_local_labels(text, label_replacements)
        if not text:
            continue
        refs = _event_refs(event, ref_by_subject_id, roles={"ACTOR", "TARGET"})
        key = (text, tuple(refs))
        if key not in seen_performance:
            seen_performance.add(key)
            performance.append({"text": text, "people": refs})

    return people, performance


def _shot_performance_details(
    shot: Mapping[str, Any],
    label_replacements: Mapping[str, str],
) -> dict[str, str] | None:
    """从 Fusion 已落库的 ShotLocalSubject.search_hint 聚合 H3 结构化表演事实。"""

    keys = {
        "expression": "expression_summary",
        "posture": "posture_summary",
        "gaze": "gaze_summary",
        "interaction": "interaction_summary",
    }
    result: dict[str, str] = {}
    for output_key, source_key in keys.items():
        values: list[str | None] = []
        for presence in _records(shot.get("subjects")):
            raw_hint = presence.get("search_hint")
            hint = raw_hint if isinstance(raw_hint, Mapping) else {}
            value = _clean_text(hint.get(source_key), limit=1200)
            values.append(_replace_local_labels(value, label_replacements))
        joined = _unique_join(values, limit=2000)
        if joined:
            result[output_key] = joined
    return result or None


def _shot_dialogue(
    shot: Mapping[str, Any],
    ref_by_subject_id: Mapping[str, str],
    *,
    run_id: str,
) -> tuple[list[dict[str, Any]], int]:
    """只把 ASR-origin DIALOGUE 带入用户结果；其它来源的“对白”一律不冒充 ASR 真相。"""

    dialogue: list[dict[str, Any]] = []
    ignored_non_asr = 0
    for event in sorted(_records(shot.get("events")), key=_event_sort_key):
        if str(event.get("event_type") or "").strip().upper() != "DIALOGUE":
            continue
        origin = str(event.get("origin") or "").strip().upper()
        if origin != "ASR":
            ignored_non_asr += 1
            continue
        text = _verbatim_text(event.get("content_text"))
        if not text:
            continue
        start_us, end_us = _range(event, "DIALOGUE event")
        source_language = str(event.get("language") or "").strip() or None
        dialogue.append({
            "dialogue_group_id": _dialogue_group_id(run_id, event),
            "start_us": start_us,
            "end_us": end_us,
            "text": text,
            "source_language": source_language,
            "speakers": _event_refs(event, ref_by_subject_id, roles={"SPEAKER"}),
        })
    return dialogue, ignored_non_asr


def _shot_ocr(shot: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """OCR 与对白分开输出，并只接受 OCR-origin event。"""

    rows: list[dict[str, Any]] = []
    ignored_non_ocr = 0
    for event in sorted(_records(shot.get("events")), key=_event_sort_key):
        if str(event.get("event_type") or "").strip().upper() != "OCR":
            continue
        origin = str(event.get("origin") or "").strip().upper()
        if origin != "OCR":
            ignored_non_ocr += 1
            continue
        text = _verbatim_text(event.get("content_text"))
        if not text:
            continue
        start_us, end_us = _range(event, "OCR event")
        rows.append({"start_us": start_us, "end_us": end_us, "text": text})
    return rows, ignored_non_ocr


def _shot_props(
    shot: Mapping[str, Any],
    label_replacements: Mapping[str, str],
) -> list[dict[str, Any]]:
    """只使用已经投影到当前 Shot 的 prop_occurrences，不从 Scene prop_hints 猜 Shot 出现。"""

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for occurrence in _records(shot.get("prop_occurrences")):
        hint = occurrence.get("prop_hint")
        if not isinstance(hint, Mapping):
            continue
        label = _clean_text(hint.get("label_hint"), limit=300)
        if not label:
            continue
        interaction = _clean_text(occurrence.get("interaction_summary"), limit=1000)
        interaction = _replace_local_labels(interaction, label_replacements)
        marker = (label.casefold(), (interaction or "").casefold())
        if marker in seen:
            continue
        seen.add(marker)
        result.append({"label": label, "interaction": interaction})
    return result


def _cinematography(shot: Mapping[str, Any]) -> dict[str, Any]:
    metadata = shot.get("model_metadata")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    return {
        "shot_type": _display_shot_type(shot.get("shot_type_hint")),
        "camera_angle": _clean_text(metadata_map.get("camera_angle_hint"), limit=256),
        "composition": _clean_text(metadata_map.get("composition_hint"), limit=500),
        "camera_motion": _display_camera_motion(shot.get("camera_motion_hint")),
        "lighting": _clean_text(metadata_map.get("lighting_hint"), limit=1000),
    }


def _continuity(shot: Mapping[str, Any], label_replacements: Mapping[str, str]) -> str | None:
    metadata = shot.get("model_metadata")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    value = _clean_text(metadata_map.get("continuity_hint"), limit=1500)
    return _replace_local_labels(value, label_replacements)


def _source_media(shot: Mapping[str, Any]) -> tuple[str | None, str | None]:
    source = shot.get("source_shot_revision_item")
    if not isinstance(source, Mapping):
        return None, None
    thumbnail = str(source.get("thumbnail_url") or "").strip() or None
    reference = str(source.get("reference_url") or "").strip() or None
    return thumbnail, reference


def _unassigned_count(payload: Mapping[str, Any]) -> int:
    unassigned = payload.get("unassigned")
    if not isinstance(unassigned, Mapping):
        return 0
    return sum(len(value) for value in unassigned.values() if isinstance(value, list))


def assemble_scene_timeline_v1(payload: Mapping[str, Any]) -> dict[str, Any]:
    """把一个 Serializer Draft payload 纯确定性转换为 ``scene-timeline-v1``。

    任何结构性矛盾（重复 Scene/Shot ordinal、非法时间、Shot 跑出所属 Scene）都会 fail closed，
    因为 G2 的职责是整理而不是“修复”或猜测 G1 真相。轻度缺失（例如某 Shot 没有可靠 visual）
    则保留空值并给用户可理解的汇总 warning。
    """

    if not isinstance(payload, Mapping):
        raise SceneTimelineAssemblyError("Breakdown payload 必须是 object")
    run = payload.get("run")
    if not isinstance(run, Mapping):
        raise SceneTimelineAssemblyError("Breakdown payload.run 缺失")

    run_id = _required_text(run.get("id"), "BreakdownRun.id")
    revision_id = _required_text(run.get("source_shot_revision_id"), "BreakdownRun.source_shot_revision_id")
    episode_id = _required_text(run.get("episode_id"), "BreakdownRun.episode_id")
    status = _required_text(run.get("status"), "BreakdownRun.status")
    is_current = bool(run.get("is_current"))

    segments = _records(payload.get("scene_segments"))
    segments.sort(key=lambda item: _required_int(item.get("ordinal"), "SceneSegment.ordinal"))

    seen_scene_ordinals: set[int] = set()
    seen_shot_ordinals: set[int] = set()
    scenes: list[dict[str, Any]] = []
    missing_visual_count = 0
    ignored_non_asr_dialogue_count = 0
    ignored_non_ocr_count = 0

    for segment in segments:
        scene_ordinal = _required_int(segment.get("ordinal"), "SceneSegment.ordinal")
        if scene_ordinal < 1 or scene_ordinal in seen_scene_ordinals:
            raise SceneTimelineAssemblyError("Scene ordinal 必须为正数且不能重复")
        seen_scene_ordinals.add(scene_ordinal)
        scene_start_us, scene_end_us = _range(segment, f"Scene {scene_ordinal}")

        people, ref_by_subject_id, label_replacements = _person_context(segment)
        location = _clean_text(segment.get("location_hint"), limit=500)
        environment = _clean_text(segment.get("environment_description"), limit=3000)
        environment = _replace_local_labels(environment, label_replacements)
        story_summary = _clean_text(segment.get("summary"), limit=4000)
        story_summary = _replace_local_labels(story_summary, label_replacements)

        source_segment_id = str(segment.get("id") or "").strip()
        shots = _records(segment.get("shots"))
        shots.sort(key=lambda item: _required_int(item.get("shot_ordinal_snapshot"), "Shot.ordinal"))
        timeline_shots: list[dict[str, Any]] = []

        for shot in shots:
            shot_ordinal = _required_int(shot.get("shot_ordinal_snapshot"), "Shot.ordinal")
            if shot_ordinal < 1 or shot_ordinal in seen_shot_ordinals:
                raise SceneTimelineAssemblyError("Episode 内 Shot ordinal 必须为正数且不能重复")
            seen_shot_ordinals.add(shot_ordinal)

            shot_scene_id = str(shot.get("scene_segment_id") or "").strip()
            if source_segment_id and shot_scene_id and shot_scene_id != source_segment_id:
                raise SceneTimelineAssemblyError(f"Shot {shot_ordinal} scene_segment_id 与所属 Scene 不一致")

            shot_start_us, shot_end_us = _range(shot, f"Shot {shot_ordinal}")
            if shot_start_us < scene_start_us or shot_end_us > scene_end_us:
                raise SceneTimelineAssemblyError(f"Shot {shot_ordinal} 时间范围超出所属 Scene")

            shot_summary = _clean_text(shot.get("summary"), limit=4000)
            shot_summary = _replace_local_labels(shot_summary, label_replacements)
            narrative_function = _clean_text(shot.get("narrative_function_hint"), limit=1000)
            narrative_function = _replace_local_labels(narrative_function, label_replacements)

            visual = _clean_text(shot.get("visual_description"), limit=4000)
            if not visual:
                visual = shot_summary
            visual = _replace_local_labels(visual, label_replacements)
            if not visual:
                missing_visual_count += 1

            shot_people, performance = _shot_people_and_performance(
                shot,
                ref_by_subject_id,
                label_replacements,
            )
            performance_details = _shot_performance_details(shot, label_replacements)
            dialogue, ignored_dialogue = _shot_dialogue(shot, ref_by_subject_id, run_id=run_id)
            on_screen_text, ignored_ocr = _shot_ocr(shot)
            ignored_non_asr_dialogue_count += ignored_dialogue
            ignored_non_ocr_count += ignored_ocr
            thumbnail_url, reference_url = _source_media(shot)

            timeline_shots.append({
                "ordinal": shot_ordinal,
                "start_us": shot_start_us,
                "end_us": shot_end_us,
                "duration_us": shot_end_us - shot_start_us,
                "thumbnail_url": thumbnail_url,
                "reference_url": reference_url,
                "summary": shot_summary,
                "narrative_function": narrative_function,
                "visual_description": visual,
                "people": shot_people,
                "performance": performance,
                "performance_details": performance_details,
                "dialogue": dialogue,
                "props": _shot_props(shot, label_replacements),
                "cinematography": _cinematography(shot),
                "continuity": _continuity(shot, label_replacements),
                "on_screen_text": on_screen_text,
            })

        scenes.append({
            "ordinal": scene_ordinal,
            "start_us": scene_start_us,
            "end_us": scene_end_us,
            "duration_us": scene_end_us - scene_start_us,
            "title": location or f"场景 {scene_ordinal:02d}",
            "scene_info": {
                "location": location,
                "interior_exterior": _display_space(segment.get("interior_exterior")),
                "time_of_day": _display_time(segment.get("time_of_day")),
                "environment": environment,
            },
            "people": people,
            "story_summary": story_summary,
            "shots": timeline_shots,
        })

    warnings: list[str] = []
    unassigned_count = _unassigned_count(payload)
    if unassigned_count:
        warnings.append(f"有 {unassigned_count} 条 G1 草稿记录尚未归入 Scene Timeline，主结果未擅自补齐。")
    if missing_visual_count:
        warnings.append(f"有 {missing_visual_count} 个镜头缺少可靠画面描述，已保留为空。")
    if ignored_non_asr_dialogue_count:
        warnings.append(f"有 {ignored_non_asr_dialogue_count} 条非 ASR 来源对白事件未进入最终对白。")
    if ignored_non_ocr_count:
        warnings.append(f"有 {ignored_non_ocr_count} 条非 OCR 来源文字事件未进入画面文字。")

    result = {
        "schema_version": SCENE_TIMELINE_SCHEMA_VERSION,
        "source_breakdown_run_id": run_id,
        "source_shot_revision_id": revision_id,
        "episode_id": episode_id,
        "status": status,
        "is_current": is_current,
        "scene_count": len(scenes),
        "shot_count": sum(len(scene["shots"]) for scene in scenes),
        "warnings": warnings,
        "scenes": scenes,
    }

    return SceneTimelinePayloadV1.model_validate(result).model_dump(mode="json")


__all__ = ["SceneTimelineAssemblyError", "assemble_scene_timeline_v1"]
