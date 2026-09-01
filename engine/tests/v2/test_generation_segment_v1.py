from __future__ import annotations

import pytest

from engine.app.generation_segment_v1 import _h3_duration_us, _split_target_windows
from engine.app.h3_runtime_v1 import H3RuntimeManager


def test_h3_duration_quantizes_to_supported_whole_seconds() -> None:
    assert _h3_duration_us(1_250_000) == 4_000_000
    assert _h3_duration_us(4_000_000) == 4_000_000
    assert _h3_duration_us(4_000_001) == 5_000_000
    assert _h3_duration_us(14_200_000) == 15_000_000
    assert _h3_duration_us(15_000_000) == 15_000_000
    with pytest.raises(ValueError):
        _h3_duration_us(15_000_001)


def test_long_target_shot_is_balanced_into_h3_sized_segments() -> None:
    windows = _split_target_windows(10_000_000, 16_000_000)
    assert windows == [(10_000_000, 18_000_000), (18_000_000, 26_000_000)]
    assert all(0 < end - start <= 15_000_000 for start, end in windows)

    windows = _split_target_windows(0, 31_000_000)
    assert len(windows) == 3
    assert windows[0][0] == 0
    assert windows[-1][1] == 31_000_000
    assert all(0 < end - start <= 15_000_000 for start, end in windows)


def test_runtime_rejects_invalid_h3_conditions_before_network_call() -> None:
    manager = H3RuntimeManager()
    with pytest.raises(ValueError):
        manager.submit_video(
            mode="FL2VA",
            prompt="test",
            conditions=[{"type": "video", "uri": "file:///tmp/reference.mp4", "role": "reference"}],
            duration_seconds=5,
        )
    with pytest.raises(ValueError):
        manager.submit_video(
            mode="REF2VA",
            prompt="test",
            conditions=[{"type": "audio", "uri": "file:///tmp/voice.wav", "role": "reference"}],
            duration_seconds=5,
        )
