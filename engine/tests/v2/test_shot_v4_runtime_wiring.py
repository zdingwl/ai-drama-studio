from __future__ import annotations

from engine.app import media_v2, media_v4, media_v5, media_v51
from engine.app.reference_render_v4 import render_reference_exact


def test_formal_media_v2_entry_is_wired_to_v51_transvlm_cache_layer() -> None:
    assert media_v2.detect_episode_shots is media_v51.detect_episode_shots
    assert media_v2.detect_episode_shots is not media_v5.detect_episode_shots
    assert media_v2.detect_episode_shots is not media_v4.detect_episode_shots
    assert media_v2._render_reference is render_reference_exact


def test_frame_pts_reader_is_zero_based_wrapper(monkeypatch) -> None:
    # 包级 wiring 后 reader 必须把第一帧 PTS 归零；这里直接检查函数契约。
    from engine.app import reference_render_v4

    values = reference_render_v4.normalized_frame_pts(None, lambda _path: (2_000_000, 2_040_000, 2_080_000))
    assert values == (0, 40_000, 80_000)
