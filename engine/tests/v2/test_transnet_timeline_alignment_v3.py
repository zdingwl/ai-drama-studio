from __future__ import annotations

import pytest

from engine.app.media_v2 import MediaPipelineError, _align_transnet_timeline, _is_transnet_decode_error


def test_transnet_and_ffprobe_one_frame_tail_drift_is_allowed() -> None:
    scores = list(range(1660))
    pts = tuple(index * 40_000 for index in range(1659))

    aligned_scores, aligned_pts = _align_transnet_timeline(scores, pts)

    assert len(aligned_scores) == 1659
    assert len(aligned_pts) == 1659
    assert aligned_scores[-1] == 1658
    assert aligned_pts[-1] == 1658 * 40_000


def test_transnet_and_ffprobe_two_frame_tail_drift_is_allowed() -> None:
    scores = list(range(100))
    pts = tuple(index * 40_000 for index in range(98))

    aligned_scores, aligned_pts = _align_transnet_timeline(scores, pts)

    assert len(aligned_scores) == 98
    assert len(aligned_pts) == 98


def test_large_frame_count_drift_is_rejected() -> None:
    scores = list(range(100))
    pts = tuple(index * 40_000 for index in range(96))

    with pytest.raises(MediaPipelineError, match="超过允许的尾帧误差"):
        _align_transnet_timeline(scores, pts)


def test_frame_count_mismatch_is_not_misclassified_as_decode_corruption() -> None:
    error = MediaPipelineError("TransNetV2 帧数 1660 与 FFprobe 帧数 1659 不一致")

    assert _is_transnet_decode_error(error) is False
