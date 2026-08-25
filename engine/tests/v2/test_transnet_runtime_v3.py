from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.app import transnet_runtime_v3 as runtime


def test_decode_transnet_frames_surfaces_real_ffmpeg_stderr(monkeypatch) -> None:
    """职责：FFmpeg 失败时任务错误必须包含真正 stderr，不能退回 generic ffmpeg-python 文案。"""

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ffmpeg"],
            returncode=1,
            stdout=b"",
            stderr=b"[h264 @ 000001] Invalid NAL unit size\nError while decoding stream #0:0",
        )

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    with pytest.raises(runtime.TransNetRuntimeError) as exc_info:
        runtime.decode_transnet_frames(Path("proxy.mp4"))

    message = str(exc_info.value)
    assert "TransNetV2 输入视频 FFmpeg 解码失败" in message
    assert "Invalid NAL unit size" in message
    assert "Error while decoding stream" in message


def test_decode_transnet_frames_rejects_incomplete_raw_frame(monkeypatch) -> None:
    """职责：FFmpeg 返回非完整 48x27x3 rawvideo 时不能继续喂给模型。"""

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ffmpeg"],
            returncode=0,
            stdout=b"12345",
            stderr=b"",
        )

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    with pytest.raises(runtime.TransNetRuntimeError, match="输入帧数据不完整"):
        runtime.decode_transnet_frames(Path("proxy.mp4"))
