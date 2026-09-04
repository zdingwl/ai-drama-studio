#!/usr/bin/env python3
"""Local-index Scene-segment Window Context contract for Fast Grounded Breakdown.

Segment v3 removed the token-heavy per-Shot scene objects, but its model contract still asked Qwen
for Episode-global Shot ordinals. Real Window-only acceptance proved that ordinal interpretation is
not reliable enough: every Window returned a small JSON object, yet segment ranges could fall
outside the frozen target ordinals.

v4 removes Episode identifiers from the model contract completely. Qwen sees only 1-based positions
inside the current Window (1..N). This adapter deterministically maps those local indexes back to the
frozen Shot ordinals/revision_item_id values before Exact-Shot grounding and E6 consume the result.
The continuous-video pass also owns conservative per-Shot camera-motion extraction because motion
cannot be established from the static Exact-Shot frame samples. Exact-Shot visible truth and all
downstream safety rules remain unchanged.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_breakdown_vlm_fast_grounded_qwen3 as fast

WINDOW_CONTEXT_PROMPT_PROFILE = "breakdown-p2-vlm-window-context-segment-index-zh-v4"
_ALLOWED_BOUNDARY_BASIS = {"WINDOW_START", "DIRECT", "CONTEXT", "UNCERTAIN"}
_ALLOWED_INTERIOR_EXTERIOR = {"INT", "EXT", "MIXED", "UNKNOWN"}


def _window_shots(window: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return tuple(fast._window_shots(window))


def _boundary_text(window: Mapping[str, Any]) -> str:
    return "\n".join(
        "- index={index}: {start:.3f}s→{end:.3f}s".format(
            index=index,
            start=fast._safe_float(shot.get("window_start_seconds")),
            end=fast._safe_float(shot.get("window_end_seconds")),
        )
        for index, shot in enumerate(_window_shots(window), start=1)
    )


def _segment_prompt(source_language: str, window: Mapping[str, Any]) -> str:
    language = (source_language or "und").strip() or "und"
    shot_count = len(_window_shots(window))
    return f"""你是短剧跨镜 Scene/匿名人物连续性分析器。输入是一段连续视频窗口。
原始语言：{language}。只输出一个合法 JSON object；不要 Markdown，不要解释，不要额外字段。

【窗口内 Shot 位置】
{_boundary_text(window)}

本窗口共有 {shot_count} 个 Shot。下面所有 index 都是“窗口内位置”，范围只能是 1..{shot_count}；
不要输出 Episode 全局 Shot 编号，不要输出 revision_item_id。

主要任务是跨镜上下文；Exact-Shot 图片将在下一阶段单独负责当前 Shot 的人物、动作、道具、构图和可见事实。
这个连续视频窗口额外负责一个静态图片无法可靠判断的事实：每个 Shot 的真实运镜。

硬规则：
1. 切镜不等于换场；特写、背景虚化、插入镜头不自动换场。
2. scene_segments 必须按 index 顺序、无重叠、无缺口地覆盖 1..{shot_count}。
3. 同一真实空间连续镜头合成一个 Scene 段，不要逐 Shot 重复输出。
4. 第一段 boundary_basis 必须 WINDOW_START；它不代表换场。
5. 后续段只有看见明确空间切换证据才用 DIRECT；仅靠上下文推测用 CONTEXT/UNCERTAIN。
6. 匿名人物只记录稳定外观与出现位置，不猜姓名/Character ID；动作、表情、姿态、说话、屏幕位置不是身份依据。
7. subject_continuity_hints 最多6项，只保留跨>=2个 Shot 的主要重复人物；appearance_summary<=24字。
8. prop_continuity_hints 最多3项，只保留跨>=2个 Shot 的剧情相关重复道具。
9. shot_motion_hints 必须覆盖 1..{shot_count} 每个 Shot；只根据该 Shot 在连续视频中的真实画面运动判断。可写“静止、推近、拉远、左摇、右摇、上摇、下摇、左移、右移、跟拍、手持晃动、复合运动、UNKNOWN”等简短事实；切镜本身不是运镜。不确定写 UNKNOWN。
10. 不从前后 Shot 把某个运镜复制给当前 Shot；一个 index 只对应自己的时间范围。
11. window_summary<=24字；location_hint<=16字。不要对白/OCR文字。
12. Scene 段最多6项；能合并就合并。

JSON schema：
{{
  "window_summary":"<=24字",
  "scene_segments":[{{
    "start_index":1,
    "end_index":{shot_count},
    "boundary_basis":"WINDOW_START|DIRECT|CONTEXT|UNCERTAIN",
    "location_hint":"<=16字地点或空字符串",
    "interior_exterior":"INT|EXT|MIXED|UNKNOWN",
    "time_of_day":"白天|夜晚|未知"
  }}],
  "subject_continuity_hints":[{{
    "appearance_summary":"<=24字稳定外观",
    "shot_indexes":[1,2]
  }}],
  "prop_continuity_hints":[{{
    "label":"道具名",
    "shot_indexes":[1,2]
  }}],
  "shot_motion_hints":[{{
    "index":1,
    "camera_motion":"静止|推近|拉远|左摇|右摇|上摇|下摇|左移|右移|跟拍|手持晃动|复合运动|UNKNOWN"
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


def _indexes(value: Any, *, shot_count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for raw in value:
        index = fast._safe_int(raw)
        if 1 <= index <= shot_count and index not in result:
            result.append(index)
    return result


def _subject_hints(raw: Any, shots: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[:6]:
        if not isinstance(item, Mapping):
            continue
        indexes = _indexes(item.get("shot_indexes"), shot_count=len(shots))
        if len(indexes) < 2:
            continue
        appearance = " ".join(str(item.get("appearance_summary") or "").strip().split())[:120]
        if not appearance:
            continue
        result.append({
            "appearance_summary": appearance,
            "continuity_summary": "",
            "shot_ordinals": [fast._safe_int(shots[index - 1].get("ordinal")) for index in indexes],
            "members": [],
        })
    return result


def _prop_hints(raw: Any, shots: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[:3]:
        if not isinstance(item, Mapping):
            continue
        indexes = _indexes(item.get("shot_indexes"), shot_count=len(shots))
        if len(indexes) < 2:
            continue
        label = " ".join(str(item.get("label") or "").strip().split())[:80]
        if not label:
            continue
        result.append({
            "label": label,
            "continuity_summary": "",
            "shot_ordinals": [fast._safe_int(shots[index - 1].get("ordinal")) for index in indexes],
        })
    return result


def _motion_hints(raw: Any, shots: tuple[Mapping[str, Any], ...]) -> dict[int, str]:
    """Normalize local-index camera motion and require exact Window coverage."""

    if not isinstance(raw, list):
        raise ValueError("segment-index shot_motion_hints must be a list")
    by_index: dict[int, str] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        index = fast._safe_int(item.get("index"))
        if index < 1 or index > len(shots) or index in by_index:
            raise ValueError("segment-index shot_motion_hints has invalid/duplicate index")
        motion = " ".join(str(item.get("camera_motion") or "UNKNOWN").strip().split())[:64]
        by_index[index] = motion or "UNKNOWN"
    if set(by_index) != set(range(1, len(shots) + 1)):
        raise ValueError("segment-index shot_motion_hints must cover every Window position exactly once")
    return by_index


def expand_segments(value: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
    """Validate local-index v4 segments and expand them into canonical legacy Window hints."""

    shots = _window_shots(window)
    if not shots:
        raise ValueError("segment-index window has no target Shots")
    shot_count = len(shots)
    real_ordinals = [fast._safe_int(shot.get("ordinal")) for shot in shots]
    if any(ordinal <= 0 for ordinal in real_ordinals) or len(set(real_ordinals)) != shot_count:
        raise ValueError("segment-index frozen Shot ordinals are invalid")

    raw_segments = value.get("scene_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("segment-index scene_segments must be a non-empty list")
    if len(raw_segments) > 6:
        raise ValueError("segment-index scene_segments exceeds maximum 6")

    normalized: list[tuple[int, int, str, dict[str, Any]]] = []
    for position, raw in enumerate(raw_segments):
        if not isinstance(raw, Mapping):
            raise ValueError("segment-index scene segment must be an object")
        start = fast._safe_int(raw.get("start_index"))
        end = fast._safe_int(raw.get("end_index"))
        if start < 1 or end < start or end > shot_count:
            raise ValueError(
                f"segment-index range outside Window positions: start={start}, end={end}, valid=1..{shot_count}"
            )
        basis = str(raw.get("boundary_basis") or "UNCERTAIN").strip().upper()
        if basis not in _ALLOWED_BOUNDARY_BASIS:
            basis = "UNCERTAIN"
        if position == 0:
            basis = "WINDOW_START"
        normalized.append((start, end, basis, _normalize_scene(raw)))

    normalized.sort(key=lambda item: item[0])
    covered: list[int] = []
    for start, end, _basis, _scene in normalized:
        covered.extend(range(start, end + 1))
    if covered != list(range(1, shot_count + 1)):
        raise ValueError("segment-index scene_segments must cover every Window position exactly once")

    motion_by_index = _motion_hints(value.get("shot_motion_hints"), shots)
    segment_for_index: dict[int, tuple[int, str, dict[str, Any]]] = {}
    for start, end, basis, scene in normalized:
        for index in range(start, end + 1):
            segment_for_index[index] = (start, basis, scene)

    shot_scene_hints: list[dict[str, Any]] = []
    canonical_motion_hints: list[dict[str, Any]] = []
    for index, shot in enumerate(shots, start=1):
        ordinal = fast._safe_int(shot.get("ordinal"))
        item_id = str(shot.get("revision_item_id") or "").strip()
        if not item_id:
            raise ValueError("segment-index target Shot missing revision_item_id")
        segment_start, boundary_basis, scene = segment_for_index[index]
        if index == segment_start and boundary_basis == "DIRECT" and index != 1:
            continuity = "NEW_SCENE"
            scene_basis = "DIRECT"
        elif index == segment_start and index != 1 and boundary_basis in {"CONTEXT", "UNCERTAIN"}:
            continuity = "UNCERTAIN"
            scene_basis = boundary_basis
        else:
            continuity = "SAME"
            scene_basis = "CONTEXT"
        camera_motion = motion_by_index[index]
        shot_scene_hints.append({
            "revision_item_id": item_id,
            "ordinal": ordinal,
            "scene_continuity": continuity,
            "scene_basis": scene_basis,
            "context_note": "",
            "camera_motion_hint": camera_motion,
            "scene": dict(scene),
        })
        canonical_motion_hints.append({
            "revision_item_id": item_id,
            "ordinal": ordinal,
            "camera_motion_hint": camera_motion,
        })

    return {
        "window_summary": " ".join(str(value.get("window_summary") or "").strip().split())[:160],
        "scene_change_candidates": [],
        "subject_continuity_hints": _subject_hints(value.get("subject_continuity_hints"), shots),
        "prop_continuity_hints": _prop_hints(value.get("prop_continuity_hints"), shots),
        "shot_motion_hints": canonical_motion_hints,
        "shot_scene_hints": shot_scene_hints,
        "scene_segments": [
            {
                "start_index": start,
                "end_index": end,
                "start_ordinal": real_ordinals[start - 1],
                "end_ordinal": real_ordinals[end - 1],
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
