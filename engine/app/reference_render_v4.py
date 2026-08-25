"""Shot V4 Reference Clip 精确渲染。

职责：
- Source / Proxy 业务时间轴都以第一帧为 0；
- FFmpeg 使用 accurate input seek 到 Shot 起点，避免每个 Shot 都从原片 0 秒重复解码；
- seek 后再用 filter trim 的排他 end 控制视频/音频长度；
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
    """精确生成一个 [start_us, start_us + duration_us) Reference Clip。

    输入：Source + Source-domain 起点/时长；输出：独立 MP4。
    为什么：旧 ``-ss + -t`` 由输出时长舍入控制，可能把 end 边界帧编码进上一 Shot。
    V4 仍使用 FFmpeg accurate seek 提升性能，但最终视频/音频结束都由 trim filter 的排他 end 控制。
    """

    output.parent.mkdir(parents=True, exist_ok=True)
    start_s = start_us / 1_000_000
    duration_s = duration_us / 1_000_000
    info = v2.probe_media(source)

    # 输入 -ss 在转码模式下默认使用 accurate_seek：会回退到关键帧解码并丢弃起点前内容。
    # 进入 filter 后再统一归零，因此 trim 只需要处理本 Shot 的 [0, duration)。
    video_filter = (
        "[0:v:0]setpts=PTS-STARTPTS,"
        f"trim=start=0:end={duration_s:.6f},"
        "setpts=PTS-STARTPTS[v]"
    )
    command = ["ffmpeg", "-y", "-ss", f"{start_s:.6f}", "-i", str(source)]
    if info.get("has_audio"):
        audio_filter = (
            "[0:a:0]asetpts=PTS-STARTPTS,"
            f"atrim=start=0:end={duration_s:.6f},"
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
