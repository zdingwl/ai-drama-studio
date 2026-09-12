import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.errors import AppError


@dataclass(frozen=True)
class SynthesizedAudio:
    audio_bytes: bytes
    mime_type: str
    file_extension: str
    remote_job_id: str | None = None


@dataclass(frozen=True)
class ProbedAudio:
    duration_us: int
    sample_rate_hz: int | None
    channel_count: int | None


class OpenAICompatibleTTSProvider:
    provider_name = "openai-compatible-tts"

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.p14_tts_base_url.rstrip("/")
        self.api_key = settings.p14_tts_api_key.get_secret_value() if settings.p14_tts_api_key else None
        self.model_name = settings.p14_tts_model
        self.response_format = settings.p14_tts_response_format
        self.timeout_seconds = settings.p14_tts_request_timeout_seconds
        if not self.base_url.startswith(("http://", "https://")):
            raise AppError("P14_TTS_RUNTIME_INVALID", "P14 TTS base URL 必须是 http(s)", status_code=500)
        if not self.model_name.strip():
            raise AppError("P14_TTS_RUNTIME_INVALID", "P14 TTS model 未配置", status_code=500)

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "base_url": self.base_url,
            "response_format": self.response_format,
        }

    def synthesize(self, *, text: str, voice_id: str) -> SynthesizedAudio:
        headers = {"Accept": "audio/*"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name,
            "input": text,
            "voice": voice_id,
            "response_format": self.response_format,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/audio/speech",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AppError("P14_TTS_TRANSPORT_FAILED", "TTS Provider 连接失败", status_code=502) from exc
        if response.status_code >= 400:
            raise AppError(
                "P14_TTS_PROVIDER_REJECTED",
                f"TTS Provider 返回 HTTP {response.status_code}",
                status_code=502,
            )
        if not response.content:
            raise AppError("P14_TTS_EMPTY_AUDIO", "TTS Provider 返回空音频", status_code=502)
        content_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0].strip().lower()
        extension = {
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/ogg": "ogg",
            "audio/flac": "flac",
            "audio/aac": "aac",
        }.get(content_type, self.response_format.strip().lower() or "wav")
        remote_job_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        return SynthesizedAudio(
            audio_bytes=response.content,
            mime_type=content_type or "application/octet-stream",
            file_extension=extension,
            remote_job_id=remote_job_id,
        )


def probe_audio(settings: Settings, path: Path) -> ProbedAudio:
    try:
        completed = subprocess.run(
            [
                settings.ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,channels:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=settings.media_probe_timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppError("P14_AUDIO_PROBE_FAILED", "无法执行 ffprobe 验证目标配音", status_code=500) from exc
    if completed.returncode != 0:
        raise AppError(
            "P14_AUDIO_PROBE_FAILED",
            "ffprobe 无法读取目标配音媒体",
            status_code=422,
            details={"stderr": completed.stderr[-500:]},
        )
    try:
        payload = json.loads(completed.stdout)
        duration_seconds = float(payload.get("format", {}).get("duration") or 0)
        stream = (payload.get("streams") or [{}])[0]
        sample_rate = int(stream["sample_rate"]) if stream.get("sample_rate") else None
        channels = int(stream["channels"]) if stream.get("channels") else None
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("P14_AUDIO_PROBE_INVALID", "ffprobe 返回的目标配音信息无效", status_code=422) from exc
    duration_us = int(round(duration_seconds * 1_000_000))
    if duration_us <= 0:
        raise AppError("P14_AUDIO_DURATION_INVALID", "目标配音真实时长必须大于 0", status_code=422)
    return ProbedAudio(duration_us=duration_us, sample_rate_hz=sample_rate, channel_count=channels)
