#!/usr/bin/env python3
"""Compact Window Context prompt for Fast Grounded Breakdown.

The previous Window prompt asked Qwen3-VL to emit several prose-heavy fields for every overlapping
window. Real acceptance on a 30-Shot Episode showed 12/12/9-Shot windows all reaching the 1600-token
cap and returning truncated JSON, while the 7-Shot window completed at 1442 tokens.

This v2 prompt keeps only information consumed by production grounding/Fusion:
- a very short window summary for scene context;
- recurring anonymous-subject continuity hints;
- recurring plot-prop continuity hints;
- one compact scene hint per frozen Shot.

Exact-Shot visible truth is unchanged and remains authoritative for people/actions/props/framing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import run_breakdown_vlm_fast_grounded_qwen3 as fast

WINDOW_CONTEXT_PROMPT_PROFILE = "breakdown-p2-vlm-window-context-compact-zh-v2"


def _compact_window_prompt(source_language: str, window: Mapping[str, Any]) -> str:
    language = (source_language or "und").strip() or "und"
    return f"""你是短剧跨镜连续性分析器。输入是一段连续视频窗口。
原始语言：{language}。只输出一个合法 JSON object；不要 Markdown，不要解释，不要额外字段。

【Shot 边界】
{fast._shot_boundary_text(window)}

只做跨镜上下文，不写逐 Shot 画面描述。Exact-Shot 图片会在下一阶段单独负责可见人物、动作、道具和构图。

硬规则：
1. 切镜不等于换场；特写、背景虚化、插入镜头不能自动判换场。
2. 只有明确地点变化、INT/EXT 改变或直接视觉证据才写 NEW_SCENE。
3. 匿名人物只记录稳定外观和出现 Shot；不猜姓名/Character ID。
4. 表情、动作、姿态、说话、屏幕左右位置不是身份依据。
5. 不转录对白、字幕、招牌、手机文字。
6. 输出必须紧凑：window_summary<=40字；appearance_summary<=40字；location_hint<=20字。
7. subject_continuity_hints 最多8项，只保留跨>=2个 Shot 的主要重复人物。
8. prop_continuity_hints 最多4项，只保留跨>=2个 Shot 的剧情相关重复道具。
9. shot_scene_hints 必须覆盖窗口内每个 Shot，revision_item_id 原样复制且每个只出现一次。
10. 不输出 context_note、environment_description、continuity_summary、scene_change_candidates。

JSON schema：
{{
  "window_summary":"<=40字",
  "subject_continuity_hints":[{{
    "appearance_summary":"<=40字稳定外观",
    "shot_ordinals":[1,2]
  }}],
  "prop_continuity_hints":[{{
    "label":"道具名",
    "shot_ordinals":[1,2]
  }}],
  "shot_scene_hints":[{{
    "revision_item_id":"必须原样复制",
    "ordinal":1,
    "scene_continuity":"SAME|NEW_SCENE|UNCERTAIN",
    "scene_basis":"DIRECT|CONTEXT|MIXED|UNCERTAIN",
    "scene":{{
      "location_hint":"<=20字地点或空字符串",
      "interior_exterior":"INT|EXT|MIXED|UNKNOWN",
      "time_of_day":"白天|夜晚|未知"
    }}
  }}]
}}
"""


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
    """Run one compact Window Context generation using the existing model/vision stack."""

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
            {"type": "text", "text": _compact_window_prompt(source_language, window)},
        ],
    }]
    value = fast._generate_json(
        model=model,
        processor=processor,
        messages=messages,
        max_new_tokens=max_new_tokens,
    )
    raw_hints = value.get("shot_scene_hints")
    if not isinstance(raw_hints, list):
        raise ValueError("compact window shot_scene_hints must be a list")
    expected_ids = {
        str(shot.get("revision_item_id") or "").strip()
        for shot in fast._window_shots(window)
        if str(shot.get("revision_item_id") or "").strip()
    }
    returned_ids = [
        str(item.get("revision_item_id") or "").strip()
        for item in raw_hints
        if isinstance(item, Mapping) and str(item.get("revision_item_id") or "").strip()
    ]
    if len(returned_ids) != len(expected_ids) or set(returned_ids) != expected_ids:
        raise ValueError(
            "compact window shot_scene_hints must cover every target Shot exactly once by revision_item_id"
        )
    return value


__all__ = ["WINDOW_CONTEXT_PROMPT_PROFILE", "_compact_window_prompt", "analyze_window"]
