"""AI Drama Studio engine.app 包级运行时接线。

02 拉片当前正式基线：V5 TransVLM-first。
- main.py / task_routes_v2.py 继续从 media_v2 导入稳定兼容入口；
- 包初始化时把正式 Shot Detection 切到 media_v5.detect_episode_shots；
- V4.1 frame-exact Reference Renderer 继续作为正式媒体渲染层；
- Source / Proxy 逐帧 PTS 统一以第一帧为 0，避免原片非零 start_time 造成系统性边界偏移；
- media_v4 只保留历史/测试兼容，不再参与正式自动 Shot Detection。
"""
from __future__ import annotations

from engine.app import media_v2 as _media_v2
from engine.app import media_v4 as _media_v4
from engine.app import media_v5 as _media_v5
from engine.app.reference_render_v4 import normalized_frame_pts as _normalized_frame_pts
from engine.app.reference_render_v4 import render_reference_exact as _render_reference_exact_v4

_original_frame_pts_reader = _media_v2._frame_pts_us


def _frame_pts_zero_based(path):
    return _normalized_frame_pts(path, _original_frame_pts_reader)


_media_v2._frame_pts_us = _frame_pts_zero_based
_media_v2.detect_episode_shots = _media_v5.detect_episode_shots
_media_v2._render_reference = _render_reference_exact_v4
_media_v4.render_reference_exact = _render_reference_exact_v4
