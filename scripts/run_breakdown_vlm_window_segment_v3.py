#!/usr/bin/env python3
"""Segment-based Window Context contract for Fast Grounded Breakdown.

Compact v2 still required one repeated scene object per Shot. Real Window-only acceptance showed
that this O(Shot-count) output shape could still hit the 1600-token cap. v3 asks Qwen3-VL for a
small number of Scene segments plus anonymous continuity hints, then deterministically expands the
segments back into the legacy ``shot_scene_hints`` shape consumed by Exact-Shot grounding and E6.

Exact-Shot visible truth is unchanged. The adapter never invents revision_item_id values: they come
only from the frozen Window manifest.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import run_breakdown_vlm_fast_grounded_qwen3 as fast

WINDOW_CONTEXT_PROMPT_PROFILE = "breakdown-p2-vlm-window-context-segment-zh-v3"
_ALLOWED_BOUNDARY_BASIS = {"WINDOW_START", "DIRECT", "CONTEXT", "UNCERTAIN"}
_ALLOWED_INTERIOR_EXTERIOR = {"INT", "EXT", "MIXED", "UNKNOWN"}


def _window_ordinals(window: Mapping[str, Any]) -> tuple[int, ...]:
    return tuple(
        fast._safe_int(shot.get("ordinal"))
        for shot in fast._window_shots(window)
        if fast._safe_int(shot.get("ordinal")) > 0
    )


def _boundary_text(window: Mapping[str, Any]) -> str:
    return "\n".join(
        "- Shot {ordinal}: {start:.3f}s→{end:.3f}s".format(
            ordinal=fast._safe_int(shot.get("ordinal")),
            start=fast._safe_float(shot.get("window_start_seconds")),
            end=fast._safe_float(shot.get("window_end_seconds")),
        )
        for shot in fast._window_shots(window)
    )


def _segment_prompt(source_language: str, window: Mapping[str, Any]) -> str:
    language = (source_language or "und").strip() or "und"
    return f"""你是短剧跨镜 Scene/匿名人物连续性分析器。输入是一段连续视频窗口。
原始语言：{language}。只输出一个合法 JSON object；不要 Markdown，不要解释，不要额外字段。

【Shot 边界】
{_boundary_text(window)}

只做跨镜上下文。Exact-Shot 图片将在下一阶段单独负责当前 Shot 的人物、动作、道具、构图和可见事实。

硬规则：
1. 切镜不等于换场；特写、背景虚化、插入镜头不自动换场。
2. scene_segments 必须按 Shot 顺序、无重叠、无缺口地覆盖窗口全部 Shot。
3. 同一真实空间连续镜头合成一个 Scene 段，不要逐 Shot 重复输出。
4. 第一段 boundary_basis 必须 WINDOW_START；它不代表换场。
5. 后续段只有看见明确空间切换证据才用 DIRECT；仅靠上下文推测用 CONTEXT/UNCERTAIN。
6. 匿名人物只记录稳定外观与出现 Shot，不猜姓名/Character ID；动作、表情、姿态、说话、屏幕位置不是身份依据。
7. subject_continuity_hints 最多6项，只保留跨>=2个 Shot 的主要重复人物；appearance_summary<=24字。
8. prop_continuity_hints 最多3项，只保留跨>=2个 Shot 的剧情相关重复道具。
9. window_summary<=24字；location_hint<=16字。不要对白/OCR文字。
10. Scene 段最多6项；能合并就合并。不要输出 revision_item_id、context_note、environment_description。

JSON schema：
{{
  "window_summary":"<=24字",
  "scene_segments":[{{
    "start_ordinal":1,
    "end_ordinal":12,
    "boundary_basis":"WINDOW_START|DIRECT|CONTEXT|UNCERTAIN",
    "location_hint":"<=16字地点或空字符串",
    "interior_exterior":"INT|EXT|MIXED|UNKNOWN",
    "time_of_day":"白天|夜晚|未知"
  }}],
  "subject_continuity_hints":[{{
    "appearance_summary":"<=24字稳定外观",
    "shot_ordinals":[1,2]
  }}],
  "prop_continuity_hints":[{{
    "label":"道具名",
    "shot_ordinals":[1,2]
  }}]
}}
"""


def _normalize_scene(raw: Mapping[str, Any]) -> dict[str, Any]:
    interior = str(raw.get("interior_exterior") or "UNKNOWN").strip().upper()
    if interior not in _ALLOWED_INTERIOR_EXTERIOR:
        interior = "UNKNOWN"
    return {
        "location_hint": " ".join(str(raw.get("location_hint") or "").strip().split())[:80],
        "interior_exterior": interior,
        "time_of_day": " ".join(str(raw.get("time_of_day") or "未知").strip().split())[:32] or "未知",
        "environment_description": "",
    }


def expand_segments(value: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
    """Validate v3 Scene segments and expand them into canonical legacy Window hints."""

    shots = tuple(fast._window_shots(window))
    if not shots:
        raise ValueError("segment window has no target Shots")
    ordinals = _window_ordinals(window)
    if len(ordinals) != len(shots) or len(set(ordinals)) != len(ordinals):
        raise ValueError("segment window Shot ordinals are invalid")
    ordinal_pos = {ordinal: index for index, ordinal in enumerate(ordinals)}

    raw_segments = value.get("scene_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("segment window scene_segments must be a non-empty list")
    if len(raw_segments) > 6:
        raise ValueError("segment window scene_segments exceeds maximum 6")

    normalized: list[tuple[int, int, str, dict[str, Any]]] = []
    for index, raw in enumerate(raw_segments):
        if not isinstance(raw, Mapping):
            raise ValueError("segment window scene segment must be an object")
        start = fast._safe_int(raw.get("start_ordinal"))
        end = fast._safe_int(raw.get("end_ordinal"))
        if start not in ordinal_pos or end not in ordinal_pos or ordinal_pos[start] > ordinal_pos[end]:
            raise ValueError("segment window scene segment range is outside target Shots")
        basis = str(raw.get("boundary_basis") or "UNCERTAIN").strip().upper()
        if basis not in _ALLOWED_BOUNDARY_BASIS:
            basis = "UNCERTAIN"
        if index == 0:
            basis = "WINDOW_START"
        normalized.append((start, end, basis, _normalize_scene(raw)))

    normalized.sort(key=lambda item: ordinal_pos[item[0]])
    covered: list[int] = []
    for start, end, _basis, _scene in normalized:
        covered.extend(ordinals[ordinal_pos[start]:ordinal_pos[end] + 1])
    if tuple(covered) != ordinals:
        raise ValueError("segment window scene_segments must cover every target Shot exactly once")

    segment_for_ordinal: dict[int, tuple[int, str, dict[str, Any]]] = {}
    for start, end, basis, scene in normalized:
        for ordinal in ordinals[ordinal_pos[start]:ordinal_pos[end] + 1]:
            segment_for_ordinal[ordinal] = (start, basis, scene)

    shot_scene_hints: list[dict[str, Any]] = []
    for shot in shots:
        ordinal = fast._safe_int(shot.get("ordinal"))
        item_id = str(shot.get("revision_item_id") or "").strip()
        if not item_id:
            raise ValueError("segment window target Shot missing revision_item_id")
        segment_start, boundary_basis, scene = segment_for_ordinal[ordinal]
        if ordinal == segment_start and boundary_basis == "DIRECT" and ordinal != ordinals[0]:
            continuity = "NEW_SCENE"
            scene_basis = "DIRECT"
        elif ordinal == segment_start and ordinal != ordinals[0] and boundary_basis in {"CONTEXT", "UNCERTAIN"}:
            continuity = "UNCERTAIN"
            scene_basis = boundary_basis
        else:
            continuity = "SAME"
            scene_basis = "CONTEXT"
        shot_scene_hints.append({
            "revision_item_id": item_id,
            "ordinal": ordinal,
            "scene_continuity": continuity,
            "scene_basis": scene_basis,
            "context_note": "",
            "scene": dict(scene),
        })

    return {
        "window_summary": " ".join(str(value.get("window_summary") or "").strip().split())[:160],
        "scene_change_candidates": [],
        "subject_continuity_hints": (
            list(value.get("subject_continuity_hints") or [])[:6]
            if isinstance(value.get("subject_continuity_hints"), list)
            else []
        ),
        "prop_continuity_hints": (
            list(value.get("prop_continuity_hints") or [])[:3]
            if isinstance(value.get("prop_continuity_hints"), list)
            else []
        ),
        "shot_scene_hints": shot_scene_hints,
        "scene_segments": [
            {
                "start_ordinal": start,
                "end_ordinal": end,
                "boundary_basis": basis,
                "scene": dict(scene),
            }
            for start, end, basis, scene in normalized
        ],
    }


def analyze_window(
    *,
    model: Any,
    processor: Any,
    window: Mapping[str, Any],
    source_language: str,
    fps: float,
    max_pixels: int,
    max_new_tokens: int,
) -> Mapping[str, Any]:
    video_path = Path(str(window.get("video_path") or ""))
    if not video_path.is_file():
        raise FileNotFoundError("Episode window clip missing")
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "video",
                "video": fast._media_ref(video_path),
                "fps": float(fps),
                "max_pixels": int(max_pixels),
            },
            {"type": "text", "text": _segment_prompt(source_language, window)},
        ],
    }]
    value = fast._generate_json(
        model=model,
        processor=processor,
        messages=messages,
        max_new_tokens=max_new_tokens,
    )
    return expand_segments(value, window)


__all__ = [
    "WINDOW_CONTEXT_PROMPT_PROFILE",
    "_segment_prompt",
    "analyze_window",
    "expand_segments",
]
