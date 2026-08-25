from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.app.media_v2 import MediaPipelineError, _is_transnet_decode_error, _validate_video_decode


def test_transnet_decode_error_classifier_detects_h264_corruption() -> None:
    assert _is_transnet_decode_error(MediaPipelineError("TransNetV2 输入视频 FFmpeg 解码失败：Invalid NAL unit size"))
    assert _is_transnet_decode_error(MediaPipelineError("Error splitting the input into NAL units"))
    assert not _is_transnet_decode_error(MediaPipelineError("TransNetV2 权重文件缺失"))


def test_validate_video_decode_surfaces_ffmpeg_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            stderr="[h264] Invalid NAL unit size (100 > 20).\nError splitting the input into NAL units.",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaPipelineError) as exc_info:
        _validate_video_decode(Path("broken-proxy.mp4"), label="新分析 Proxy")

    message = str(exc_info.value)
    assert "新分析 Proxy完整解码校验失败" in message
    assert "Invalid NAL unit size" in message


def test_validate_video_decode_accepts_clean_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _validate_video_decode(Path("clean-proxy.mp4"), label="新分析 Proxy")
