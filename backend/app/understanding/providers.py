import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.understanding.schemas import EpisodeUnderstandingSemantic


@dataclass(frozen=True)
class EpisodeUnderstandingInput:
    source_path: Path
    source_filename: str
    mime_type: str
    episode_id: str
    episode_order: int
    duration_us: int
    source_language: str | None
    evidence_payload: dict
    shot_hints: list[dict]


@dataclass(frozen=True)
class EpisodeUnderstandingProviderResult:
    semantic: EpisodeUnderstandingSemantic
    remote_job_id: str | None


class SourceEpisodeUnderstandingProvider(Protocol):
    provider_name: str
    model_name: str

    @property
    def profile(self) -> dict: ...

    def analyze(self, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingProviderResult: ...


def _iter_file(path: Path, chunk_size: int = 4 * 1024 * 1024):
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _gemini_response_schema() -> dict:
    allowed = {
        "$id", "$defs", "$ref", "$anchor", "type", "format", "title", "description", "enum",
        "items", "prefixItems", "minItems", "maxItems", "minimum", "maximum", "anyOf", "oneOf",
        "properties", "additionalProperties", "required",
    }

    def clean(value):
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, nested in value.items():
            if key not in allowed:
                continue
            if key in {"properties", "$defs"}:
                result[key] = {name: clean(schema) for name, schema in nested.items()}
            else:
                result[key] = clean(nested)
        return result

    return clean(EpisodeUnderstandingSemantic.model_json_schema())


def _extract_response_text(response: dict) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini response did not contain candidates")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts if part.get("text"))
    if not text.strip():
        raise ValueError("Gemini response did not contain text")
    return text


def _prompt(payload: EpisodeUnderstandingInput) -> str:
    evidence_json = json.dumps(payload.evidence_payload, ensure_ascii=False, separators=(",", ":"))
    shot_json = json.dumps(payload.shot_hints, ensure_ascii=False, separators=(",", ":"))
    return f"""你正在执行 AI Drama Studio P7「整集多模态原片理解」。

硬约束：
1. 输入视频是完整 Episode，必须按完整时间轴理解，不得拆成独立 Shot 后再拼剧情。
2. canonical Source Evidence 是对白和画面文字的事实来源。你可以理解视频画面，但不得纠正、改写或覆盖 canonical 对白/OCR。
3. timed_script 中 dialogue_evidence_ids / visual_text_evidence_ids 只能引用下方给出的真实 ID；没有证据就留空，不得编造 ID。
4. Shot Anchors 只是可选定位提示。timed_script / story beat 的时间窗口是语义窗口，允许重叠，绝不能假装是精确 Shot Boundary。
5. 不要根据视频音轨自行补写对白；对白事实以 Source Evidence 为准。可利用非语言声音辅助理解情绪，但不得形成新的 canonical 文本事实。
6. 所有时间使用微秒，范围必须位于 0 到 {payload.duration_us} 之间。
7. 输出必须严格符合给定 JSON Schema，不要输出 Markdown、解释或额外字段。
8. 内容使用与原片相适应的自然中文表达；人物名无法确认时使用稳定候选名（如“女主候选”），不要伪造身份。

Episode:
- episode_id: {payload.episode_id}
- episode_order: {payload.episode_order}
- source_filename: {payload.source_filename}
- duration_us: {payload.duration_us}
- source_language: {payload.source_language or 'unknown'}

CURRENT Source Evidence:
{evidence_json}

Optional Shot Anchor hints（只用于定位/去歧义，不是语义分段边界）:
{shot_json}
"""


class GeminiSourceEpisodeUnderstandingProvider:
    provider_name = "google-gemini"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_gemini_model
        if settings.p7_gemini_api_key is None or not settings.p7_gemini_api_key.get_secret_value().strip():
            raise AppError(
                "P7_PROVIDER_NOT_CONFIGURED",
                "P7 Gemini Provider 尚未配置 AI_DRAMA_P7_GEMINI_API_KEY",
                status_code=409,
            )

    @property
    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "base_url": self.settings.p7_gemini_base_url,
            "video_input": "FILES_API_FULL_EPISODE",
            "structured_output": "JSON_SCHEMA",
            "prompt_version": "p7-source-bible-v1",
        }

    @property
    def _api_key(self) -> str:
        assert self.settings.p7_gemini_api_key is not None
        return self.settings.p7_gemini_api_key.get_secret_value()

    def _wait_until_active(self, client: httpx.Client, file_info: dict) -> dict:
        current = file_info
        deadline = time.monotonic() + self.settings.p7_gemini_processing_timeout_seconds
        while str(current.get("state") or "ACTIVE").upper() == "PROCESSING":
            if time.monotonic() >= deadline:
                raise TimeoutError("Gemini file processing timed out")
            time.sleep(self.settings.p7_gemini_poll_interval_seconds)
            name = str(current.get("name") or "")
            if not name:
                raise ValueError("Gemini upload response missing file name")
            response = client.get(
                f"{self.settings.p7_gemini_base_url.rstrip('/')}/v1beta/{name}",
                headers={"x-goog-api-key": self._api_key},
            )
            response.raise_for_status()
            current = response.json()
        if str(current.get("state") or "ACTIVE").upper() not in {"ACTIVE", "STATE_UNSPECIFIED"}:
            raise ValueError(f"Gemini file processing failed: {current.get('state')}")
        return current

    def analyze(self, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingProviderResult:
        base_url = self.settings.p7_gemini_base_url.rstrip("/")
        size_bytes = payload.source_path.stat().st_size
        timeout = httpx.Timeout(self.settings.p7_gemini_request_timeout_seconds)
        file_name: str | None = None
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            start = client.post(
                f"{base_url}/upload/v1beta/files",
                headers={
                    "x-goog-api-key": self._api_key,
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(size_bytes),
                    "X-Goog-Upload-Header-Content-Type": payload.mime_type,
                    "Content-Type": "application/json",
                },
                json={"file": {"display_name": payload.source_filename[:512]}},
            )
            start.raise_for_status()
            upload_url = start.headers.get("x-goog-upload-url")
            if not upload_url:
                raise ValueError("Gemini resumable upload URL missing")
            upload = client.post(
                upload_url,
                headers={
                    "Content-Length": str(size_bytes),
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                content=_iter_file(payload.source_path),
            )
            upload.raise_for_status()
            upload_payload = upload.json()
            file_info = upload_payload.get("file") or upload_payload
            file_info = self._wait_until_active(client, file_info)
            file_name = str(file_info.get("name") or "") or None
            file_uri = str(file_info.get("uri") or "")
            file_mime = str(file_info.get("mimeType") or file_info.get("mime_type") or payload.mime_type)
            if not file_uri:
                raise ValueError("Gemini upload response missing file URI")

            try:
                response = client.post(
                    f"{base_url}/v1beta/models/{self.model_name}:generateContent",
                    headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                    json={
                        "contents": [
                            {
                                "role": "user",
                                "parts": [
                                    {"fileData": {"mimeType": file_mime, "fileUri": file_uri}},
                                    {"text": _prompt(payload)},
                                ],
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": 32768,
                            "responseMimeType": "application/json",
                            "responseJsonSchema": _gemini_response_schema(),
                        },
                    },
                )
                response.raise_for_status()
                text = _extract_response_text(response.json())
                semantic = EpisodeUnderstandingSemantic.model_validate_json(text)
                return EpisodeUnderstandingProviderResult(semantic=semantic, remote_job_id=file_name)
            finally:
                if file_name:
                    try:
                        client.delete(
                            f"{base_url}/v1beta/{file_name}",
                            headers={"x-goog-api-key": self._api_key},
                        )
                    except httpx.HTTPError:
                        pass


def build_source_episode_understanding_provider(settings: Settings) -> SourceEpisodeUnderstandingProvider:
    provider = settings.p7_understanding_provider.strip().lower()
    if provider == "gemini":
        return GeminiSourceEpisodeUnderstandingProvider(settings)
    raise AppError(
        "P7_PROVIDER_UNSUPPORTED",
        "当前 P7 Provider 未实现",
        status_code=422,
        details={"provider": settings.p7_understanding_provider},
    )
