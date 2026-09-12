import base64
import hashlib
import io
import json
import subprocess
import wave
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
    reference_audio_urls: tuple[str, ...]
    locale: str | None = None
    tags: tuple[str, ...] = ()
    catalog_gender: str = "UNKNOWN"
    catalog_age_range: str = "UNKNOWN"
    catalog_style_tags: tuple[str, ...] = ()
    catalog_description: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    usage_notice: str | None = None

    @property
    def reference_audio_url(self) -> str:
        return self.reference_audio_urls[0]

    @property
    def catalog_metadata_available(self) -> bool:
        return bool(
            self.catalog_gender != "UNKNOWN"
            or self.catalog_age_range != "UNKNOWN"
            or self.catalog_style_tags
            or self.catalog_description
        )


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
        raw_reference_audio_urls = item.get("reference_audio_urls")
        if raw_reference_audio_urls is None:
            raw_reference_audio_urls = [item.get("reference_audio_url")]
        if not isinstance(raw_reference_audio_urls, list):
            raise AppError(
                "P14_INDEXTTS_VOICE_CATALOG_INVALID",
                "IndexTTS reference_audio_urls 必须是数组",
                status_code=500,
                details={"index": index},
            )
        reference_audio_urls = tuple(str(value or "").strip() for value in raw_reference_audio_urls)
        if not voice_key or not display_name or not reference_audio_urls or any(not value for value in reference_audio_urls):
            raise AppError(
                "P14_INDEXTTS_VOICE_CATALOG_INVALID",
                "IndexTTS 参考声线条目缺少 voice_key/display_name/reference_audio_url(s)",
                status_code=500,
                details={"index": index},
            )
        if len(reference_audio_urls) > 12:
            raise AppError(
                "P14_INDEXTTS_VOICE_CATALOG_INVALID",
                "单条参考声线最多允许 12 个音频片段",
                status_code=500,
                details={"voice_key": voice_key},
            )
        if voice_key in seen:
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "IndexTTS voice_key 不能重复", status_code=500)
        for reference_audio_url in reference_audio_urls:
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
        raw_catalog_style_tags = item.get("catalog_style_tags") or []
        if not isinstance(raw_catalog_style_tags, list) or not all(isinstance(tag, str) for tag in raw_catalog_style_tags):
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "catalog_style_tags 必须是字符串数组", status_code=500)
        catalog_gender = str(item.get("catalog_gender") or "UNKNOWN").strip().upper()
        catalog_age_range = str(item.get("catalog_age_range") or "UNKNOWN").strip().upper()
        if catalog_gender not in {"UNKNOWN", "FEMALE", "MALE", "NEUTRAL"}:
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "catalog_gender 无效", status_code=500)
        if catalog_age_range not in {"UNKNOWN", "CHILD", "TEEN", "YOUNG_ADULT", "ADULT", "MATURE", "SENIOR"}:
            raise AppError("P14_INDEXTTS_VOICE_CATALOG_INVALID", "catalog_age_range 无效", status_code=500)
        locale = str(item.get("locale") or "").strip() or None
        entries.append(
            TTSVoiceCatalogEntry(
                voice_key=voice_key,
                display_name=display_name,
                reference_audio_urls=reference_audio_urls,
                locale=locale,
                tags=tuple(tag.strip() for tag in raw_tags if tag.strip()),
                catalog_gender=catalog_gender,
                catalog_age_range=catalog_age_range,
                catalog_style_tags=tuple(tag.strip() for tag in raw_catalog_style_tags if tag.strip()),
                catalog_description=str(item.get("catalog_description") or "").strip() or None,
                source_name=str(item.get("source_name") or "").strip() or None,
                source_url=str(item.get("source_url") or "").strip() or None,
                license_name=str(item.get("license_name") or "").strip() or None,
                license_url=str(item.get("license_url") or "").strip() or None,
                usage_notice=str(item.get("usage_notice") or "").strip() or None,
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
                "catalog_gender": item.catalog_gender,
                "catalog_age_range": item.catalog_age_range,
                "catalog_style_tags": list(item.catalog_style_tags),
                "catalog_description": item.catalog_description,
                "catalog_metadata_available": item.catalog_metadata_available,
                "source_name": item.source_name,
                "source_url": item.source_url,
                "license_name": item.license_name,
                "license_url": item.license_url,
                "usage_notice": item.usage_notice,
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
                "reference_audio_urls": list(item.reference_audio_urls),
                "locale": item.locale,
                "tags": list(item.tags),
                "catalog_gender": item.catalog_gender,
                "catalog_age_range": item.catalog_age_range,
                "catalog_style_tags": list(item.catalog_style_tags),
                "source_name": item.source_name,
                "license_name": item.license_name,
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

    def voice_source_fingerprint(self, voice_key: str) -> str:
        entry = self.resolve_voice(voice_key)
        payload = (
            {"voice_key": entry.voice_key, "reference_audio_url": entry.reference_audio_url}
            if len(entry.reference_audio_urls) == 1
            else {"voice_key": entry.voice_key, "reference_audio_urls": list(entry.reference_audio_urls)}
        )
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _fetch_reference_bytes(self, source: str) -> tuple[bytes, str]:
        if source.startswith("data:audio/"):
            try:
                header, encoded = source.split(",", 1)
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考音频 data URL 无效", status_code=500) from exc
            if not raw:
                raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考音频为空", status_code=500)
            return raw, header[5:].split(";", 1)[0]

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
        return response.content, content_type if content_type.startswith("audio/") else "audio/wav"

    @staticmethod
    def _concatenate_wav_clips(clips: list[bytes]) -> bytes:
        output = io.BytesIO()
        expected: tuple[int, int, int, str] | None = None
        frames: list[bytes] = []
        try:
            for raw in clips:
                with wave.open(io.BytesIO(raw), "rb") as reader:
                    parameters = (
                        reader.getnchannels(),
                        reader.getsampwidth(),
                        reader.getframerate(),
                        reader.getcomptype(),
                    )
                    if expected is None:
                        expected = parameters
                    elif parameters != expected:
                        raise AppError(
                            "P14_INDEXTTS_REFERENCE_FORMAT_MISMATCH",
                            "同一参考声线的多个 WAV 片段采样参数不一致",
                            status_code=422,
                        )
                    if reader.getcomptype() != "NONE":
                        raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "参考声线 WAV 必须是未压缩 PCM", status_code=422)
                    frames.append(reader.readframes(reader.getnframes()))
            if expected is None:
                raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "参考声线音频为空", status_code=422)
            with wave.open(output, "wb") as writer:
                writer.setnchannels(expected[0])
                writer.setsampwidth(expected[1])
                writer.setframerate(expected[2])
                writer.setcomptype("NONE", "not compressed")
                for frame_bytes in frames:
                    writer.writeframes(frame_bytes)
        except wave.Error as exc:
            raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "参考声线包含无效 WAV 音频", status_code=422) from exc
        return output.getvalue()

    def _reference_data_url(self, voice_key: str) -> tuple[str, str]:
        cached = self._reference_cache.get(voice_key)
        if cached is not None:
            return cached
        entry = self.resolve_voice(voice_key)
        fetched = [self._fetch_reference_bytes(source) for source in entry.reference_audio_urls]
        if len(fetched) == 1:
            raw, mime = fetched[0]
        else:
            raw = self._concatenate_wav_clips([item[0] for item in fetched])
            mime = "audio/wav"
        if len(raw) > 25 * 1024 * 1024:
            raise AppError("P14_INDEXTTS_REFERENCE_TOO_LARGE", "拼接后的 IndexTTS 参考音频超过 25MB", status_code=422)
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        sha = hashlib.sha256(raw).hexdigest()
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
