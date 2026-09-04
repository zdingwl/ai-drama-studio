#!/usr/bin/env python3
"""Reconstruction-safe compact Exact-Shot grounding contract v3.

Compact v2 substantially reduced generation cost, but real selected-batch acceptance exposed a
quality regression on Shot 1: the visible description correctly mentioned blue roses and a glass
vase while ``props`` remained empty. v3 keeps the same compact/local-index architecture, preserves
salient reconstruction objects, and now also extracts the Shot-level directing facts needed by H3:
angle, lighting and structured performance (expression/posture/gaze/interaction).

The model still never emits frozen revision_item_id values or internal anonymous subject labels.
Those remain deterministic host-side compatibility fields. Camera motion is intentionally not
inferred from static frames; the Episode-window temporal pass owns that fact.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

import run_breakdown_vlm_fast_grounded_qwen3 as fast

EXACT_SHOT_PROMPT_PROFILE = "breakdown-p2-vlm-exact-shot-presence-zh-v4"
_ALLOWED_IE = {"INT", "EXT", "MIXED", "UNKNOWN"}
_ALLOWED_VISIBILITY = {"FULL", "PARTIAL", "OCCLUDED", "BACK_VIEW", "UNKNOWN"}
_ALLOWED_IMPORTANCE = {"LOW", "MEDIUM", "HIGH"}


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _subject_label(index: int) -> str:
    if 1 <= index <= 26:
        return f"subject_{chr(ord('A') + index - 1)}"
    return f"subject_{index}"


def _compact_scene_contexts(
    batch: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    canonical = fast._grounding_scene_contexts(batch, windows, window_results)
    rows: list[dict[str, Any]] = []
    for local_index, shot in enumerate(batch, start=1):
        item_id = str(shot.get("revision_item_id") or "").strip()
        contexts: list[dict[str, Any]] = []
        for raw in canonical.get(item_id, []):
            if not isinstance(raw, Mapping):
                continue
            hint = raw.get("shot_scene_hint")
            if not isinstance(hint, Mapping):
                continue
            scene = hint.get("scene") if isinstance(hint.get("scene"), Mapping) else {}
            compact = {
                "loc": _clean(scene.get("location_hint"), 40),
                "ie": str(scene.get("interior_exterior") or "UNKNOWN").strip().upper(),
                "tod": _clean(scene.get("time_of_day"), 16),
                "sc": str(hint.get("scene_continuity") or "UNCERTAIN").strip().upper(),
            }
            if compact not in contexts:
                contexts.append(compact)
        rows.append({"i": local_index, "scene_ctx": contexts[:2]})
    return rows


def _prompt(
    source_language: str,
    batch: Sequence[Mapping[str, Any]],
    scene_contexts: Sequence[Mapping[str, Any]],
) -> str:
    import json

    language = (source_language or "und").strip() or "und"
    targets = ", ".join(
        f"{index}=EpisodeShot{fast._safe_int(shot.get('ordinal'))}"
        for index, shot in enumerate(batch, start=1)
    )
    context_json = json.dumps(scene_contexts, ensure_ascii=False, separators=(",", ":"))
    return f"""你是短剧 Exact-Shot 视觉事实提取器。原始语言：{language}。
只输出一个合法 JSON object，不要 Markdown、解释、额外字段。

本批 ShotIndex：{targets}
Scene上下文（只可补地点/INT-EXT/时间/同场景连续关系，不能搬入邻镜人物动作道具）：{context_json}

随后图片按 ShotIndex 分组；每组图片只属于该 Shot。

硬规则：
1. visible / people / props / shot_type / angle / composition / lighting 只能来自当前 Shot 图片。
2. 当前 Shot 看不到的人、动作、表情、姿态、视线、交互、道具绝不能从上下文补入。
3. props 不只记录“人物正在使用的剧情道具”；凡是对镜头重建重要、画面中显著且可独立识别的可见物体都必须列出，例如花束、花瓶、手机、袋子、书籍等。
4. 如果 visible 明确写到了这类具体物体，props 不能漏掉；人物没有接触该物体时 people=[]、interaction="" 即可。
5. 桌面/沙发/门等大环境结构只在它本身是镜头核心或后续重建必须保留时列 props，避免把整个背景家具清单化。
6. people 的 expression/posture/gaze/interaction 只写当前 Shot 图片直接支持的事实；看不清就写空字符串，不要从人物身份或剧情猜。
7. angle 写镜头视角/机位关系，例如平视、俯拍、仰拍、过肩、侧面、背面、顶视；无法确认写空字符串。
8. lighting 只写当前 Shot 直接可见的主光方向/软硬/明暗/色温等简短事实；无法确认写空字符串。
9. continuity 只允许根据给定 scene_ctx.sc 写“同场景延续/新场景起点”这类保守提示；不能发明服装、人物、道具连续性。UNCERTAIN 时写空字符串。
10. 不猜姓名、Character/Scene/Prop ID；people 按当前 Shot 稳定视觉顺序输出。
11. 不转录对白/OCR；说话真相由 ASR 负责。
12. 静态采样图不能可靠判断推/拉/摇/移，因此不要输出 camera motion；程序统一记 UNKNOWN，运镜由视频窗口阶段补充。
13. visible<=80字；appearance<=32字；activity<=24字；expression/posture/gaze/interaction<=20字；composition<=24字；angle<=12字；lighting<=28字；continuity<=24字。
14. 每个 ShotIndex 必须且只能输出一次。不要输出 revision_item_id、人物身份标签、跨镜人物标签、events、长解释。
15. 逐帧枚举所有可见的人，包括前景背身、侧身、遮挡、贴边、只露头肩或躯干的人。不能只列正脸、正在说话或能认出身份的人；背身人物的表情可空，但 people 不能漏掉。不能把两个人合成一个外观描述。
16. 同一人在不同采样帧只列一个 people 条目；无法确认是同一人时不要强行合并。只在实际出现的帧列 frame_boxes，frame 是本 Shot 从 1 开始的图片序号，box 是该帧整个可见人体的 [x,y,width,height]，坐标除以原图宽高归一化到 0..1。不能把脸框当全身框，也不能搬用别帧的位置。不能定位时 frame_boxes=[]，不要编造框。

JSON schema：
{{
  "shots":[{{
    "i":1,
    "scene":{{"loc":"地点或空","ie":"INT|EXT|MIXED|UNKNOWN","tod":"白天|夜晚|未知"}},
    "visible":"当前Shot核心可见事实",
    "shot_type":"特写|近景|中景|全景|远景|空",
    "angle":"平视|俯拍|仰拍|过肩|侧面|背面|顶视|空",
    "composition":"简短构图或空",
    "lighting":"当前Shot可见光线事实或空",
    "continuity":"同场景延续|新场景起点|空",
    "people":[{{
      "appearance":"稳定可见外观",
      "activity":"当前可见动作",
      "expression":"当前可见表情或空",
      "posture":"当前可见姿态或空",
      "gaze":"当前可见视线或空",
      "interaction":"当前可见人物/道具交互或空",
      "position":"左侧|中央|右侧|前景|背景|UNKNOWN",
      "visibility":"FULL|PARTIAL|OCCLUDED|BACK_VIEW|UNKNOWN",
      "frame_boxes":[{{"frame":1,"box":[0.1,0.2,0.3,0.6]}}]
    }}],
    "props":[{{
      "label":"对镜头重建重要的显著可见物体",
      "importance":"LOW|MEDIUM|HIGH",
      "people":[1],
      "interaction":"与人物的可见关系或空"
    }}]
  }}]
}}
"""


def _messages(
    *,
    source_language: str,
    batch: Sequence[Mapping[str, Any]],
    scene_contexts: Sequence[Mapping[str, Any]],
    max_pixels: int,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": _prompt(source_language, batch, scene_contexts),
    }]
    for local_index, shot in enumerate(batch, start=1):
        ordinal = fast._safe_int(shot.get("ordinal"))
        content.append({"type": "text", "text": f"ShotIndex {local_index} / EpisodeShot {ordinal}"})
        frames = shot.get("frames")
        if not isinstance(frames, list) or not frames:
            raise ValueError(f"Shot {ordinal} has no grounding frames")
        for frame_index, raw in enumerate(frames, start=1):
            if not isinstance(raw, Mapping):
                continue
            path = Path(str(raw.get("path") or ""))
            if not path.is_file():
                raise FileNotFoundError(f"Shot {ordinal} frame missing")
            content.append({"type": "text", "text": f"ShotIndex {local_index} frame {frame_index}"})
            content.append({
                "type": "image",
                "image": fast._media_ref(path),
                "max_pixels": int(max_pixels),
            })
    return [{"role": "user", "content": content}]


def _canonical_subjects(raw: Any) -> list[dict[str, Any]]:
    from engine.app.person_presence_geometry_v1 import frame_boxes
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:12], start=1):
        if not isinstance(item, Mapping):
            continue
        visibility = str(item.get("visibility") or "UNKNOWN").strip().upper()
        if visibility not in _ALLOWED_VISIBILITY:
            visibility = "UNKNOWN"
        result.append({
            "label": _subject_label(index),
            "appearance_summary": _clean(item.get("appearance"), 160),
            "activity_summary": _clean(item.get("activity"), 160),
            "expression_summary": _clean(item.get("expression"), 160),
            "posture_summary": _clean(item.get("posture"), 160),
            "gaze_summary": _clean(item.get("gaze"), 160),
            "interaction_summary": _clean(item.get("interaction"), 160),
            "screen_position": _clean(item.get("position"), 48) or "UNKNOWN",
            "visibility": visibility,
            "speaking_state": "UNKNOWN",
            "frame_boxes": frame_boxes(item.get("frame_boxes")),
        })
    return result


def _canonical_props(raw: Any, subject_count: int) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw[:12]:
        if not isinstance(item, Mapping):
            continue
        label = _clean(item.get("label"), 160)
        marker = label.casefold()
        if not label or marker in seen:
            continue
        seen.add(marker)
        importance = str(item.get("importance") or "LOW").strip().upper()
        if importance not in _ALLOWED_IMPORTANCE:
            importance = "LOW"
        labels: list[str] = []
        indexes = item.get("people")
        if isinstance(indexes, list):
            for raw_index in indexes:
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    continue
                if 1 <= index <= subject_count:
                    label_key = _subject_label(index)
                    if label_key not in labels:
                        labels.append(label_key)
        result.append({
            "label": label,
            "importance": importance,
            "narrative_reason": _clean(item.get("interaction"), 160),
            "subject_labels": labels,
        })
    return result


def expand_compact(value: Mapping[str, Any], batch: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list):
        raise ValueError("compact exact-shot output.shots must be a list")
    by_index: dict[int, Mapping[str, Any]] = {}
    for raw in raw_shots:
        if not isinstance(raw, Mapping):
            continue
        index = fast._safe_int(raw.get("i"))
        if index < 1 or index > len(batch) or index in by_index:
            raise ValueError("compact exact-shot output has invalid/duplicate ShotIndex")
        by_index[index] = raw
    if set(by_index) != set(range(1, len(batch) + 1)):
        raise ValueError("compact exact-shot output must cover every target ShotIndex exactly once")

    result: list[dict[str, Any]] = []
    for index, target in enumerate(batch, start=1):
        raw = by_index[index]
        item_id = str(target.get("revision_item_id") or "").strip()
        if not item_id:
            raise ValueError("compact exact-shot target missing revision_item_id")
        scene_raw = raw.get("scene") if isinstance(raw.get("scene"), Mapping) else {}
        ie = str(scene_raw.get("ie") or "UNKNOWN").strip().upper()
        if ie not in _ALLOWED_IE:
            ie = "UNKNOWN"
        visible = _clean(raw.get("visible"), 1200)
        if not visible:
            raise ValueError("compact exact-shot visible description is required")
        subjects = _canonical_subjects(raw.get("people"))
        props = _canonical_props(raw.get("props"), len(subjects))
        semantic = {
            "scene": {
                "location_hint": _clean(scene_raw.get("loc"), 255),
                "interior_exterior": ie,
                "time_of_day": _clean(scene_raw.get("tod"), 64) or "未知",
                "environment_description": "",
            },
            "shot": {
                "summary": visible,
                "visual_description": visible,
                "shot_type_hint": _clean(raw.get("shot_type"), 64),
                "camera_angle_hint": _clean(raw.get("angle"), 160),
                "camera_motion_hint": "UNKNOWN",
                "lighting_hint": _clean(raw.get("lighting"), 500),
                "continuity_hint": _clean(raw.get("continuity"), 500),
                "narrative_function_hint": "",
                "composition_hint": _clean(raw.get("composition"), 160),
            },
            "subjects": subjects,
            "events": [],
            "props": props,
        }
        result.append({"revision_item_id": item_id, "semantic": semantic})
    return result


def analyze_grounding_batch(
    *,
    model: Any,
    processor: Any,
    batch: Sequence[Mapping[str, Any]],
    source_language: str,
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
    max_pixels: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    contexts = _compact_scene_contexts(batch, windows, window_results)
    value = fast._generate_json(
        model=model,
        processor=processor,
        messages=_messages(
            source_language=source_language,
            batch=batch,
            scene_contexts=contexts,
            max_pixels=max_pixels,
        ),
        max_new_tokens=max_new_tokens,
    )
    return expand_compact(value, batch)


def grounding_adaptive(
    *,
    model: Any,
    processor: Any,
    batch: Sequence[Mapping[str, Any]],
    source_language: str,
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
    max_pixels: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    targets = tuple(batch)
    try:
        return analyze_grounding_batch(
            model=model,
            processor=processor,
            batch=targets,
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
    except Exception:
        if len(targets) <= 1:
            raise
        midpoint = max(1, len(targets) // 2)
        left = grounding_adaptive(
            model=model,
            processor=processor,
            batch=targets[:midpoint],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        fast._cleanup_cuda()
        right = grounding_adaptive(
            model=model,
            processor=processor,
            batch=targets[midpoint:],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        return [*left, *right]


__all__ = [
    "EXACT_SHOT_PROMPT_PROFILE",
    "_prompt",
    "analyze_grounding_batch",
    "expand_compact",
    "grounding_adaptive",
]
