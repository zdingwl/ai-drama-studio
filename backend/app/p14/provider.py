import base64
import hashlib
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


@dataclass(frozen=True)
class TTSVoiceCatalogEntry:
    voice_key: str
    display_name: str
    reference_audio_url: str
    locale: str | None = None
    tags: tuple[str, ...] = ()


def _load_voice_catalog(raw: str) -> tuple[TTSVoiceCatalogEntry, ...]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "IndexTTS 参考声线目录不是合法 JSON", status_code=500) from exc
    if not isinstance(payload, list):
        raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "IndexTTS 参考声线目录必须是数组", status_code=500)
    entries: list[TTSVoiceCatalogEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "IndexTTS 参考声线条目必须是对象", status_code=500)
        voice_key = str(item.get("voice_key") or "").strip()
        display_name = str(item.get("display_name") or "").strip()
        reference_audio_url = str(item.get("reference_audio_url") or "").strip()
        if not voice_key or not display_name or not reference_audio_url:
            raise AppError(
                "P14_INDEXTTS_VOICE_CATALOG_INVALID",
                "IndexTTS 参考声线条目缺少 voice_key/display_name/reference_audio_url",
                status_code=500,
                details={"index": index},
            )
        if voice_key in seen:
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "IndexTTS voice_key 不能重复", status_code=500)
        if not reference_audio_url.startswith(("http://", "https://", "data:audio/")):
            raise AppError(
                "P14_INDEXTTS_VOICE_CATALOG_INVALID",
                "reference_audio_url 只允许 http(s) 或 data:audio URL",
                status_code=500,
                details={"voice_key": voice_key},
            )
        seen.add(voice_key)
        raw_tags = item.get("tags") or []
        if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "IndexTTS tags 必须是字符串数组", status_code=500)
        locale = str(item.get("locale") or "").strip() or None
        entries.append(
            TTSVoiceCatalogEntry(
                voice_key=voice_key,
                display_name=display_name,
                reference_audio_url=reference_audio_url,
                locale=locale,
                tags=tuple(tag.strip() for tag in raw_tags if tag.strip()),
            )
        )
    return tuple(entries)


def _index_language(target_language: str) -> str:
    normalized = (target_language or "").strip().lower().replace("_", "-")
    if normalized.startswith("zh"):
        return "zh"
    if normalized.startswith("en"):
        return "en"
    if normalized.startswith(("ja", "jp")):
        return "ja"
    if normalized.startswith("es"):
        return "es"
    if normalized.startswith("ar"):
        return "ar"
    raise AppError(
        "P14_INDEXTTS_LANGUAGE_UNSUPPORTED",
        "IndexTTS-2.5 当前正式支持 zh/en/ja/es/ar；项目目标语言不在支持范围",
        status_code=409,
        details={"target_language": target_language},
    )


class IndexTTS25Provider:
    provider_name = "indextts-2.5-vllm-omni"
    response_format = "wav"

    def __init__(self, settings: Settings, *, target_language: str) -> None:
        self.base_url = settings.p14_indextts_base_url.rstrip("/")
        self.model_name = settings.p14_indextts_model
        self.timeout_seconds = settings.p14_indextts_request_timeout_seconds
        self.default_speed = settings.p14_indextts_default_speed
        self.default_emo_alpha = settings.p14_indextts_default_emo_alpha
        self.target_language = target_language
        self.language_code = _index_language(target_language)
        self._voice_catalog = _load_voice_catalog(settings.p14_indextts_voice_catalog_json)
        self._voice_by_key = {item.voice_key: item for item in self._voice_catalog}
        self._reference_cache: dict[str, tuple[str, str]] = {}
        if not self.base_url.startswith(("http://", "https://")):
            raise AppError("P14_INDEXTTS_RUNTIME_INVALID", "IndexTTS base URL 必须是 http(s)", status_code=500)
        if self.model_name != "IndexTeam/IndexTTS-2.5":
            raise AppError("P14_INDEXTTS_RUNTIME_INVALID", "P14 只允许 IndexTeam/IndexTTS-2.5", status_code=500)

    def public_voice_catalog(self) -> list[dict]:
        return [
            {
                "voice_key": item.voice_key,
                "display_name": item.display_name,
                "locale": item.locale,
                "tags": list(item.tags),
            }
            for item in self._voice_catalog
        ]

    def resolve_voice(self, voice_key: str) -> TTSVoiceCatalogEntry:
        if not self._voice_catalog:
            raise AppError(
                "P14_INDEXTTS_VOICE_CATALOG_REQUIRED",
                "尚未配置 IndexTTS-2.5 参考声线，不能生成目标配音",
                status_code=409,
            )
        entry = self._voice_by_key.get(voice_key)
        if entry is None:
            raise AppError(
                "P14_INDEXTTS_VOICE_UNKNOWN",
                "选择的参考声线不在当前 IndexTTS-2.5 Voice Catalog 中",
                status_code=422,
                details={"voice_key": voice_key},
            )
        return entry

    def profile(self) -> dict:
        catalog_payload = [
            {
                "voice_key": item.voice_key,
                "display_name": item.display_name,
                "reference_audio_url": item.reference_audio_url,
                "locale": item.locale,
                "tags": list(item.tags),
            }
            for item in self._voice_catalog
        ]
        catalog_fingerprint = hashlib.sha256(
            json.dumps(catalog_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "base_url": self.base_url,
            "response_format": self.response_format,
            "target_language": self.target_language,
            "lang": self.language_code,
            "speed": self.default_speed,
            "use_emo_text": True,
            "emo_alpha": self.default_emo_alpha,
            "voice_catalog_fingerprint": catalog_fingerprint,
        }

    def _reference_data_url(self, voice_key: str) -> tuple[str, str]:
        cached = self._reference_cache.get(voice_key)
        if cached is not None:
            return cached
        entry = self.resolve_voice(voice_key)
        source = entry.reference_audio_url
        if source.startswith("data:audio/"):
            try:
                header, encoded = source.split(",", 1)
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考音频 data URL 无效", status_code=500) from exc
            if not raw:
                raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考音频为空", status_code=500)
            sha = hashlib.sha256(raw).hexdigest()
            result = (source, sha)
            self._reference_cache[voice_key] = result
            return result

        urls = [source]
        if source.startswith("https://hf-mirror.com/"):
            urls.append(source.replace("https://hf-mirror.com/", "https://huggingface.co/", 1))
        response = None
        last_error: Exception | None = None
        for url in urls:
            try:
                candidate = httpx.get(url, timeout=min(self.timeout_seconds, 120.0), follow_redirects=True)
                if candidate.status_code < 400 and candidate.content:
                    response = candidate
                    break
            except httpx.HTTPError as exc:
                last_error = exc
        if response is None:
            raise AppError("P14_INDEXTTS_REFERENCE_FETCH_FAILED", "无法读取 IndexTTS 参考音频", status_code=502) from last_error
        if len(response.content) > 25 * 1024 * 1024:
            raise AppError("P14_INDEXTTS_REFERENCE_TOO_LARGE", "IndexTTS 参考音频超过 25MB", status_code=422)
        content_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0].strip().lower()
        if content_type.startswith("text/"):
            raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考音频 URL 返回了文本内容", status_code=502)
        mime = content_type if content_type.startswith("audio/") else "audio/wav"
        data_url = f"data:{mime};base64,{base64.b64encode(response.content).decode('ascii')}"
        sha = hashlib.sha256(response.content).hexdigest()
        result = (data_url, sha)
        self._reference_cache[voice_key] = result
        return result

    def synthesize(self, *, text: str, voice_id: str) -> SynthesizedAudio:
        # `voice_id` is retained as the pre-P14-PASS wire-field name. It now means an
        # application reference-voice key, never an OpenAI/provider preset voice id.
        ref_audio, _reference_sha = self._reference_data_url(voice_id)
        payload = {
            "model": self.model_name,
            "input": text,
            "response_format": self.response_format,
            "ref_audio": ref_audio,
            "speed": self.default_speed,
            "extra_params": {
                "lang": self.language_code,
                "text_normalization": True,
                "use_emo_text": True,
                "emo_alpha": self.default_emo_alpha,
            },
        }
        try:
            response = httpx.post(
                f"{self.base_url}/audio/speech",
                json=payload,
                headers={"Accept": "audio/wav"},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AppError("P14_INDEXTTS_TRANSPORT_FAILED", "IndexTTS-2.5 服务连接失败", status_code=502) from exc
        if response.status_code >= 400:
            raise AppError(
                "P14_INDEXTTS_REJECTED",
                f"IndexTTS-2.5 返回 HTTP {response.status_code}",
                status_code=502,
            )
        if not response.content:
            raise AppError("P14_INDEXTTS_EMPTY_AUDIO", "IndexTTS-2.5 返回空音频", status_code=502)
        content_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0].strip().lower()
        remote_job_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        return SynthesizedAudio(
            audio_bytes=response.content,
            mime_type=content_type or "audio/wav",
            file_extension="wav",
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
