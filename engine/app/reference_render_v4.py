"""Shot V4 Reference Clip 帧精确渲染。

职责：
- Source / Proxy 业务时间轴都以第一帧为 0；
- Shot 的业务区间统一是 ``[start_us, end_us)``；
- 视频帧归属只按 zero-based Source PTS 对应的帧索引决定，不再用浮点秒比较决定 end；
- 左 Shot 永远拥有 ``[start_frame, cut_frame)``，右 Shot 从 ``cut_frame`` 开始；
- FFmpeg 仍可在安全位置 accurate seek，但 seek 只用于减少解码量，不参与最终帧归属判断；
- 编码后校验实际视频帧数，任何漏帧/多帧都会让本次 Shot Run 失败，旧 Current 不切换。

为什么不能只用 ``trim=end=0.920000``：
FFprobe 的真实 PTS 会被业务层转换成 integer microseconds。一个原始时间戳可能是
0.9199996s，业务上四舍五入后是 920000us，已经属于下一 Shot；但 FFmpeg 直接比较原始
浮点/有理时间戳时仍可能认为它小于 0.920000，从而把下一镜第一帧编码进上一镜。
V4.1 因此把“时间边界”转换成“Source 帧所有权”后再渲染。
"""
from __future__ import annotations

from bisect import bisect_left
from pathlib import Path

from engine.app import media_v2 as v2


def normalized_frame_pts(path: Path, original_reader) -> tuple[int, ...]:
    """把媒体第一帧归一到业务 0 点，同时保留逐帧顺序。"""

    pts = tuple(int(value) for value in original_reader(path))
    if not pts:
        return pts
    origin = pts[0]
    return tuple(max(0, value - origin) for value in pts)


def frame_span_indices(frame_pts: tuple[int, ...], start_us: int, end_us: int) -> tuple[int, int]:
    """把 ``[start_us, end_us)`` 映射为 Source 帧索引 ``[start_index, end_index)``。

    ``bisect_left`` 是这里最关键的语义：边界 PTS 等于 ``end_us`` 的帧一定落到下一 Shot，
    而边界 PTS 等于 ``start_us`` 的帧一定属于当前 Shot。相邻 Shot 使用同一个公共边界时，
    两边索引天然首尾相接，不会共享一帧，也不会漏一帧。
    """

    if not frame_pts:
        raise v2.MediaPipelineError("Source PTS 为空，无法生成帧精确 Reference Clip")
    if end_us <= start_us:
        raise v2.MediaPipelineError("Reference Clip 时间区间无效")
    if any(right < left for left, right in zip(frame_pts, frame_pts[1:])):
        raise v2.MediaPipelineError("Source PTS 非递增，无法建立稳定帧所有权")

    start_index = bisect_left(frame_pts, int(start_us))
    end_index = bisect_left(frame_pts, int(end_us))
    if start_index >= len(frame_pts):
        raise v2.MediaPipelineError("Reference Clip 起点已经超出 Source 最后一帧")
    end_index = min(len(frame_pts), end_index)
    if end_index <= start_index:
        raise v2.MediaPipelineError(
            f"Reference Clip [{start_us}, {end_us}) 内没有可归属的视频帧"
        )
    return start_index, end_index


def _safe_seek_us(frame_pts: tuple[int, ...], start_index: int, start_us: int) -> int:
    """选择第一目标帧之前、上一帧之后的安全 seek 点。

    业务 PTS 已经按微秒取整，所以不能直接 ``-ss start_us``：目标帧的原始 PTS 可能比
    取整值早不到 1us，直接 seek 有机会跳过它。取前后两帧业务 PTS 的中点，并保证不晚于
    用户业务 start，可以给 FFmpeg 足够的解码余量，同时避免从视频 0 点重复解码。
    """

    if start_index <= 0:
        return 0
    previous_us = int(frame_pts[start_index - 1])
    first_owned_us = int(frame_pts[start_index])
    midpoint_us = previous_us + max(1, (first_owned_us - previous_us) // 2)
    return max(0, min(int(start_us), midpoint_us))


def render_reference_exact(
    source: Path,
    output: Path,
    start_us: int,
    duration_us: int,
    *,
    frame_pts: tuple[int, ...] | None = None,
) -> None:
    """精确生成一个 ``[start_us, start_us + duration_us)`` Reference Clip。

    视频按 Source 帧数量裁剪；音频仍按业务微秒边界裁剪。自动拉片应传入已经读取好的
    ``frame_pts``，人工编辑没有现成 PTS 时才按需读取一次 Source PTS。
    """

    output.parent.mkdir(parents=True, exist_ok=True)
    start_us = int(start_us)
    duration_us = int(duration_us)
    end_us = start_us + duration_us
    source_pts = tuple(int(value) for value in (frame_pts if frame_pts is not None else v2._frame_pts_us(source)))
    start_index, end_index = frame_span_indices(source_pts, start_us, end_us)
    expected_frames = end_index - start_index
    seek_us = _safe_seek_us(source_pts, start_index, start_us)

    # accurate input seek 会丢弃 seek 点之前的帧。seek 被选在“上一帧之后、第一目标帧之前”，
    # 因此 filter 看到的第 0 帧就是当前 Shot 的第一 owned frame；最终只按数量取 N 帧。
    seek_s = seek_us / 1_000_000
    video_filter = (
        "[0:v:0]setpts=PTS-STARTPTS,"
        f"trim=start_frame=0:end_frame={expected_frames},"
        "setpts=PTS-STARTPTS[v]"
    )
    command = ["ffmpeg", "-y", "-ss", f"{seek_s:.6f}", "-i", str(source)]
    info = v2.probe_media(source)

    if info.get("has_audio"):
        audio_start_s = max(0, start_us - seek_us) / 1_000_000
        audio_end_s = max(start_us - seek_us, end_us - seek_us) / 1_000_000
        audio_filter = (
            "[0:a:0]asetpts=PTS-STARTPTS,"
            f"atrim=start={audio_start_s:.6f}:end={audio_end_s:.6f},"
            "asetpts=PTS-STARTPTS[a]"
        )
        command += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-fps_mode", "passthrough",
            "-c:a", "aac", "-b:a", "192k",
        ]
    else:
        command += [
            "-filter_complex", video_filter,
            "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-fps_mode", "passthrough",
        ]
    command += ["-movflags", "+faststart", str(output)]
    v2._run(command)

    # 这是 Release Gate，不是诊断信息：Reference Clip 多/少一帧都会污染后续人物、场景、
    # Dialogue 与生成参考，所以新 Run 必须直接失败，绝不能带着错误媒体切 Current。
    actual_frames = len(v2._frame_pts_us(output))
    if actual_frames != expected_frames:
        output.unlink(missing_ok=True)
        raise v2.MediaPipelineError(
            f"Reference Clip 帧数校验失败：期望 {expected_frames} 帧，实际 {actual_frames} 帧"
        )
