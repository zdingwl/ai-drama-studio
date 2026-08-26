"""AI Drama Studio engine.app 包级运行时接线。

02 拉片当前正式基线：V5.1 TransVLM-first + dependency-aware Episode cache。
- main.py / task_routes_v2.py 继续从 media_v2 导入稳定兼容入口；
- 包初始化时把正式 Shot Detection 切到 media_v51.detect_episode_shots；
- 第一次仍按官方 TransVLM 顺序运行，并安全捕获其真实 model RGB / whole-video Flow；
- 后续可按 RGB -> Flow -> raw TransVLM output -> Transition 层级复用或强制失效；
- V5.1 不改变 V5 的 Source PTS Cut 落帧和 frame-exact Reference Renderer；
- Source / Proxy 逐帧 PTS 统一以第一帧为 0，避免原片非零 start_time 造成系统性边界偏移；
- media_v4 / media_v5 保留历史与基础算法实现，不再作为正式 API 入口。
"""
from __future__ import annotations

from engine.app import media_v2 as _media_v2
from engine.app import media_v4 as _media_v4
from engine.app import media_v51 as _media_v51
from engine.app.reference_render_v4 import normalized_frame_pts as _normalized_frame_pts
from engine.app.reference_render_v4 import render_reference_exact as _render_reference_exact_v4

_original_frame_pts_reader = _media_v2._frame_pts_us


def _frame_pts_zero_based(path):
    return _normalized_frame_pts(path, _original_frame_pts_reader)


_media_v2._frame_pts_us = _frame_pts_zero_based
_media_v2.detect_episode_shots = _media_v51.detect_episode_shots
_media_v2._render_reference = _render_reference_exact_v4
_media_v4.render_reference_exact = _render_reference_exact_v4
