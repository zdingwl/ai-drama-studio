"""F03 VFR 技术回归：Proxy 不得偷偷把变帧率 Source 强制转成 CFR。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.app.preprocess import generate_proxy_video


def _frame_pts(path: Path) -> list[float]:
    """读取主视频流每帧 PTS 秒值，仅用于测试帧间隔是否仍为 VFR。"""

    payload = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=pts_time",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )
    return [float(frame["pts_time"]) for frame in payload.get("frames", []) if "pts_time" in frame]


def _frame_deltas(pts: list[float]) -> set[float]:
    """把相邻帧时间差归一到微秒级小数，避免 FFprobe 文本尾差影响断言。"""

    return {round(pts[index + 1] - pts[index], 6) for index in range(len(pts) - 1)}


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="本测试需要本机 FFmpeg/FFprobe",
)
def test_proxy_preserves_variable_frame_cadence(tmp_path: Path) -> None:
    """构造多种帧间隔的 Source，确认 F03 Proxy 仍具有多种 PTS 间隔而不是单一 CFR。"""

    source_path = tmp_path / "vfr-source.mp4"
    proxy_path = tmp_path / "proxy.mp4"

    # 前 30 帧约 30fps，后 30 帧按约 15fps 展开时间；fps_mode=vfr 保留不均匀 PTS。
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30",
            "-vf",
            "setpts='if(lt(N,30),N/(30*TB),(1+(N-30)/15)/TB)'",
            "-frames:v",
            "60",
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source_path),
        ],
        check=True,
    )

    generate_proxy_video(
        source_path=source_path,
        target_path=proxy_path,
        video_stream_index=0,
        audio_stream_index=None,
    )

    source_pts = _frame_pts(source_path)
    proxy_pts = _frame_pts(proxy_path)
    source_deltas = _frame_deltas(source_pts)
    proxy_deltas = _frame_deltas(proxy_pts)

    assert len(source_pts) == 60
    assert len(proxy_pts) == 60
    assert len(source_deltas) > 1
    assert len(proxy_deltas) > 1
    # 至少保留约 1/30s 和 1/15s 两种主要时间节奏；不允许全部变成统一 25/30fps。
    assert any(abs(delta - 1 / 30) < 0.002 for delta in proxy_deltas)
    assert any(abs(delta - 1 / 15) < 0.002 for delta in proxy_deltas)
