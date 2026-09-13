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
        raise AppError("P16_MEDIA_PROBE_FAILED", "生成视频无法通过 ffprobe 校验", status_code=502) from exc
    if duration <= 0 or width <= 0 or height <= 0 or not codec:
        raise AppError("P16_MEDIA_PROBE_INVALID", "生成视频缺少有效时长/尺寸/codec", status_code=502)
    return VideoProbe(duration_us=int(round(duration * 1_000_000)), width=width, height=height, codec_name=codec)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duration_tolerance_us() -> int:
    raw = os.getenv("AI_DRAMA_P16_DURATION_TOLERANCE_SECONDS", "1.5")
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise AppError("P16_CONFIG_INVALID", "P16 duration tolerance 配置无效", status_code=500) from exc
    if not 0 <= seconds <= 10:
        raise AppError("P16_CONFIG_INVALID", "P16 duration tolerance 必须在 0~10 秒", status_code=500)
    return int(round(seconds * 1_000_000))
