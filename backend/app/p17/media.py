import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class VideoProbe:
    duration_us: int
    width: int
    height: int
    codec_name: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_ffmpeg(args: list[str], *, code: str, message: str, timeout: int = 900) -> None:
    settings = get_settings()
    try:
        subprocess.run(
            [settings.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-y", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        raise AppError(code, message, status_code=502) from exc


def probe_video(path: Path) -> VideoProbe:
    settings = get_settings()
    try:
        result = subprocess.run(
            [
                settings.ffprobe_binary,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height:format=duration",
                "-of", "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        if not streams:
            raise ValueError("no video stream")
        stream = streams[0]
        duration = float((payload.get("format") or {}).get("duration") or 0)
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        codec = str(stream.get("codec_name") or "").strip()
    except Exception as exc:
        raise AppError("P17_MEDIA_PROBE_FAILED", "P17 输出视频无法通过 ffprobe 校验", status_code=502) from exc
    if duration <= 0 or width <= 0 or height <= 0 or not codec:
        raise AppError("P17_MEDIA_PROBE_INVALID", "P17 输出视频缺少有效时长/尺寸/codec", status_code=502)
    return VideoProbe(duration_us=int(round(duration * 1_000_000)), width=width, height=height, codec_name=codec)


def final_duration_tolerance_us() -> int:
    raw = os.getenv("AI_DRAMA_P17_DURATION_TOLERANCE_SECONDS", "0.5")
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise AppError("P17_CONFIG_INVALID", "P17 duration tolerance 配置无效", status_code=500) from exc
    if not 0 <= seconds <= 5:
        raise AppError("P17_CONFIG_INVALID", "P17 duration tolerance 必须在 0~5 秒", status_code=500)
    return int(round(seconds * 1_000_000))


def create_silence_audio(path: Path, duration_us: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(duration_us, 1) / 1_000_000
    _run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", "anullsrc=r=48000:cl=stereo",
            "-t", f"{duration:.6f}",
            "-c:a", "pcm_s16le",
            str(path),
        ],
        code="P17_AUDIO_SILENCE_FAILED",
        message="P17 无法建立 Episode 基础静音音轨",
    )


def overlay_audio(base_path: Path, clip_path: Path, output_path: Path, delay_us: int) -> None:
    samples = max(0, int(round(delay_us * 48_000 / 1_000_000)))
    filter_complex = (
        f"[1:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,"
        f"adelay={samples}S:all=1[delayed];"
        "[0:a][delayed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]"
    )
    _run_ffmpeg(
        [
            "-i", str(base_path),
            "-i", str(clip_path),
            "-filter_complex", filter_complex,
            "-map", "[mix]",
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        code="P17_AUDIO_MIX_FAILED",
        message="P17 正式 Target Audio timeline mix 失败",
    )


def extract_audio_window(source_path: Path, output_path: Path, start_us: int, duration_us: int) -> None:
    _run_ffmpeg(
        [
            "-ss", f"{max(0, start_us) / 1_000_000:.6f}",
            "-i", str(source_path),
            "-t", f"{max(1, duration_us) / 1_000_000:.6f}",
            "-ar", "48000",
            "-ac", "2",
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        code="P17_SEGMENT_AUDIO_FAILED",
        message="P17 无法提取 segment 正式对白音轨",
    )


def normalize_video(source_path: Path, output_path: Path, *, duration_us: int, width: int, height: int) -> None:
    width = max(2, width - (width % 2))
    height = max(2, height - (height % 2))
    duration = max(duration_us, 1) / 1_000_000
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"tpad=stop_mode=clone:stop_duration=20,trim=duration={duration:.6f},setpts=PTS-STARTPTS"
    )
    _run_ffmpeg(
        [
            "-i", str(source_path),
            "-vf", vf,
            "-an",
            "-r", "30",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ],
        code="P17_VIDEO_NORMALIZE_FAILED",
        message="P17 segment trim/pad/normalize 失败",
    )


def concatenate_videos(paths: list[Path], output_path: Path) -> None:
    if not paths:
        raise AppError("P17_VIDEO_SEGMENTS_EMPTY", "P17 Episode 没有可拼接视频段", status_code=409)
    list_path = output_path.with_suffix(".concat.txt")
    rows: list[str] = []
    for path in paths:
        normalized = path.resolve().as_posix().replace("'", "'\\''")
        rows.append(f"file '{normalized}'")
    list_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    try:
        _run_ffmpeg(
            [
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c:v", "copy",
                "-an",
                str(output_path),
            ],
            code="P17_VIDEO_CONCAT_FAILED",
            message="P17 Episode 视频确定性拼接失败",
        )
    finally:
        list_path.unlink(missing_ok=True)


def mux_formal_audio(video_path: Path, audio_path: Path, output_path: Path, duration_us: int) -> None:
    _run_ffmpeg(
        [
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", f"{max(1, duration_us) / 1_000_000:.6f}",
            "-movflags", "+faststart",
            str(output_path),
        ],
        code="P17_FINAL_MUX_FAILED",
        message="P17 无法把正式 Target Audio 混入 Episode 视频",
    )


def _srt_time(us: int) -> str:
    total_ms = max(0, int(round(us / 1000)))
    milliseconds = total_ms % 1000
    total_seconds = total_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def write_srt(path: Path, rows: list[tuple[int, int, int, str]]) -> None:
    blocks: list[str] = []
    for utterance_number, start_us, end_us, text in rows:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        blocks.append(f"{utterance_number}\n{_srt_time(start_us)} --> {_srt_time(end_us)}\n{normalized}")
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
