"""AI Drama Studio engine.app 包级运行时接线。

02 拉片 V4 通过这里替换 media_v2 的正式 Shot Detection / Reference Render 入口：
- 现有 main.py / task_routes_v2.py 无需维护第二套路由；
- 所有历史 import 路径继续稳定；
- shot_editor_v2 后续 import media_v2._render_reference 时，也会拿到 V4 的 [start,end) 精确渲染；
- Source / Proxy 逐帧 PTS 统一以第一帧为 0，避免原片非零 start_time 造成系统性边界偏移。
"""
from __future__ import annotations

from engine.app import media_v2 as _media_v2
from engine.app import media_v4 as _media_v4
from engine.app.reference_render_v4 import normalized_frame_pts as _normalized_frame_pts
from engine.app.reference_render_v4 import render_reference_exact as _render_reference_exact_v4

_original_frame_pts_reader = _media_v2._frame_pts_us


def _frame_pts_zero_based(path):
    return _normalized_frame_pts(path, _original_frame_pts_reader)


_media_v2._frame_pts_us = _frame_pts_zero_based
_media_v2.detect_episode_shots = _media_v4.detect_episode_shots
_media_v2._render_reference = _render_reference_exact_v4
_media_v4.render_reference_exact = _render_reference_exact_v4
