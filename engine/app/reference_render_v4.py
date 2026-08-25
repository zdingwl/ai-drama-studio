"""Shot V4 Reference Clip 精确渲染。

职责：
- 先把 Source 视频/音频 PTS 归零，再按 [start,end) trim；
- 避免原片 start_time / 首帧 PTS 非零导致 Source PTS 与 Proxy 时间轴偏移；
- end 为排他边界，下一 Shot 的第一帧不会进入上一 Shot Reference Clip。
"""
from __future__ import annotations

from pathlib import Path

from engine.app import media_v2 as v2


def normalized_frame_pts(path: Path, original_reader) -> tuple[int, ...]:
    pts = tuple(int(value) for value in original_reader(path))
    if not pts:
        return pts
    origin = pts[0]
    return tuple(max(0, value - origin) for value in pts)


def render_reference_exact(source: Path, output: Path, start_us: int, duration_us: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    end_us = start_us + duration_us
    start_s = start_us / 1_000_000
    end_s = end_us / 1_000_000
    info = v2.probe_media(source)

    # 先 setpts 归零，再 trim；第二个 setpts 把 Shot 自己重新归零用于独立播放。
    video_filter = (
        f"[0:v:0]setpts=PTS-STARTPTS,"
        f"trim=start={start_s:.6f}:end={end_s:.6f},"
        "setpts=PTS-STARTPTS[v]"
    )
    command = ["ffmpeg", "-y", "-i", str(source)]
    if info.get("has_audio"):
        audio_filter = (
            f"[0:a:0]asetpts=PTS-STARTPTS,"
            f"atrim=start={start_s:.6f}:end={end_s:.6f},"
            "asetpts=PTS-STARTPTS[a]"
        )
        command += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
        ]
    else:
        command += [
            "-filter_complex", video_filter,
            "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        ]
    command += ["-movflags", "+faststart", str(output)]
    v2._run(command)
