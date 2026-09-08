import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class VideoProbeResult:
    duration_us: int
    width: int
    height: int
    codec_name: str
    avg_frame_rate: str
    has_audio: bool
    raw: dict


def _run_media_command(args: list[str], *, timeout_seconds: int, code: str, message: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise AppError(
            "MEDIA_RUNTIME_MISSING",
            "服务器缺少 FFmpeg/ffprobe 运行时",
            status_code=503,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError(code, message, status_code=422, details={"reason": "timeout"}) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-2000:]
        raise AppError(code, message, status_code=422, details={"reason": detail})
    return result


def probe_video(path: Path) -> VideoProbeResult:
    settings = get_settings()
    result = _run_media_command(
        [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        timeout_seconds=settings.media_probe_timeout_seconds,
        code="VIDEO_PROBE_FAILED",
        message="视频无法读取或文件已损坏",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AppError("VIDEO_PROBE_FAILED", "ffprobe 返回了无效结果", status_code=422) from exc

    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video_stream is None:
        raise AppError("VIDEO_STREAM_MISSING", "文件中没有可用视频轨", status_code=422)

    duration_value = (payload.get("format") or {}).get("duration") or video_stream.get("duration")
    try:
        duration_us = int(round(float(duration_value) * 1_000_000))
    except (TypeError, ValueError):
        duration_us = 0
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if duration_us <= 0 or width <= 0 or height <= 0:
        raise AppError("VIDEO_METADATA_INVALID", "视频缺少有效时长或画面尺寸", status_code=422)

    return VideoProbeResult(
        duration_us=duration_us,
        width=width,
        height=height,
        codec_name=str(video_stream.get("codec_name") or "unknown"),
        avg_frame_rate=str(video_stream.get("avg_frame_rate") or "0/0"),
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        raw=payload,
    )


def decode_preflight(path: Path) -> None:
    settings = get_settings()
    _run_media_command(
        [
            settings.ffmpeg_binary,
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        timeout_seconds=settings.media_decode_timeout_seconds,
        code="VIDEO_DECODE_FAILED",
        message="视频无法正常解码",
    )
