import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from arkruntime import Ark

from app.core.config import Settings
from app.core.errors import AppError
from app.projects.enums import SourceUnderstandingProvider
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


def _clean_json_schema(value: Any) -> Any:
    """Keep a conservative JSON-Schema subset suitable for model prompting."""
    if isinstance(value, list):
        return [_clean_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    allowed = {
        "$defs",
        "$ref",
        "type",
        "title",
        "description",
        "enum",
        "const",
        "items",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "anyOf",
        "oneOf",
        "properties",
        "additionalProperties",
        "required",
    }
    cleaned: dict[str, Any] = {}
    for key, nested in value.items():
        if key not in allowed:
            continue
        if key in {"properties", "$defs"}:
            cleaned[key] = {name: _clean_json_schema(schema) for name, schema in nested.items()}
        else:
            cleaned[key] = _clean_json_schema(nested)
    return cleaned


def _response_schema() -> dict:
    return _clean_json_schema(EpisodeUnderstandingSemantic.model_json_schema())


def _json_text(text: str) -> str:
    value = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    if value.startswith("{") and value.endswith("}"):
        return value
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise ValueError("P7 provider response did not contain a JSON object")


def _parse_semantic(text: str) -> EpisodeUnderstandingSemantic:
    return EpisodeUnderstandingSemantic.model_validate_json(_json_text(text))


def _prompt(payload: EpisodeUnderstandingInput) -> str:
    evidence_json = json.dumps(payload.evidence_payload, ensure_ascii=False, separators=(",", ":"))
    shot_json = json.dumps(payload.shot_hints, ensure_ascii=False, separators=(",", ":"))
    schema_json = json.dumps(_response_schema(), ensure_ascii=False, separators=(",", ":"))
    return f"""你正在执行 AI Drama Studio P7「整集多模态原片理解」。

硬约束：
1. 输入视频是完整 Episode，必须按完整时间轴理解，不得拆成独立 Shot 后再拼剧情。
2. canonical Source Evidence 是对白和画面文字的事实来源。你可以理解视频画面，但不得纠正、改写或覆盖 canonical 对白/OCR。
3. timed_script 中 dialogue_evidence_ids / visual_text_evidence_ids 只能引用下方给出的真实 ID；没有证据就留空，不得编造 ID。
4. Shot Anchors 只是可选定位提示。timed_script / story beat 的时间窗口是语义窗口，允许重叠，绝不能假装是精确 Shot Boundary。
5. 不要根据视频音轨自行补写对白；对白事实以 Source Evidence 为准。可利用非语言声音辅助理解情绪，但不得形成新的 canonical 文本事实。
6. 所有时间使用微秒，范围必须位于 0 到 {payload.duration_us} 之间。
7. 只输出一个 JSON object，不要输出 Markdown、解释或额外文本。JSON 必须符合末尾 Schema。
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

Output JSON Schema:
{schema_json}
"""


def _ark_response_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None) if not isinstance(item, dict) else item.get("type")
        if item_type != "message":
            continue
        content = getattr(item, "content", None) if not isinstance(item, dict) else item.get("content")
        for part in content or []:
            part_type = getattr(part, "type", None) if not isinstance(part, dict) else part.get("type")
            if part_type != "output_text":
                continue
            text = getattr(part, "text", None) if not isinstance(part, dict) else part.get("text")
            if text:
                chunks.append(str(text))
    if not chunks:
        raise ValueError("Ark response did not contain output_text")
    return "".join(chunks)


class DoubaoSeedSourceEpisodeUnderstandingProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError(
                "P7_PROVIDER_NOT_CONFIGURED",
                "火山引擎 P7 Provider 尚未配置 AI_DRAMA_P7_DOUBAO_API_KEY",
                status_code=409,
            )

    @property
    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "CLOUD_API",
            "base_url": self.settings.p7_doubao_base_url,
            "video_input": "ARK_FILES_API_FULL_EPISODE",
            "video_fps": self.settings.p7_doubao_video_fps,
            "structured_output": "JSON_SCHEMA_PROMPT_PLUS_SERVER_VALIDATION",
            "prompt_version": "p7-source-bible-v1",
        }

    @property
    def _api_key(self) -> str:
        assert self.settings.p7_doubao_api_key is not None
        return self.settings.p7_doubao_api_key.get_secret_value()

    def analyze(self, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingProviderResult:
        client = Ark(
            api_key=self._api_key,
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        uploaded_file_id: str | None = None
        try:
            with payload.source_path.open("rb") as stream:
                uploaded = client.files.create(file=stream, purpose="user_data")
            uploaded_file_id = str(getattr(uploaded, "id", "") or "")
            if not uploaded_file_id:
                raise ValueError("Ark file upload did not return a file id")
            client.files.wait_for_processing(
                uploaded_file_id,
                max_wait_seconds=self.settings.p7_doubao_request_timeout_seconds,
            )
            response = client.responses.create(
                model=self.model_name,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_video",
                                "file_id": uploaded_file_id,
                                "fps": self.settings.p7_doubao_video_fps,
                            },
                            {"type": "input_text", "text": _prompt(payload)},
                        ],
                    }
                ],
                thinking={"type": "enabled"},
            )
            semantic = _parse_semantic(_ark_response_text(response))
            response_id = str(getattr(response, "id", "") or "") or None
            return EpisodeUnderstandingProviderResult(semantic=semantic, remote_job_id=response_id)
        finally:
            if uploaded_file_id:
                try:
                    client.files.delete(uploaded_file_id)
                except Exception:
                    # Cleanup must not turn a valid SOURCE_BIBLE result into a failed task.
                    pass


class LocalQwenSourceEpisodeUnderstandingProvider:
    provider_name = "qwen3-vl-local-vllm"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_qwen_local_model

    @property
    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "LOCAL_OPENAI_COMPATIBLE",
            "base_url": self.settings.p7_qwen_local_base_url,
            "video_input": "VLLM_FILE_URL_FULL_EPISODE",
            "structured_output": "JSON_SCHEMA_PROMPT_PLUS_SERVER_VALIDATION",
            "prompt_version": "p7-source-bible-v1",
        }

    def analyze(self, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingProviderResult:
        source_uri = payload.source_path.resolve().as_uri()
        headers = {"Content-Type": "application/json"}
        if self.settings.p7_qwen_local_api_key is not None:
            key = self.settings.p7_qwen_local_api_key.get_secret_value().strip()
            if key:
                headers["Authorization"] = f"Bearer {key}"
        timeout = httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{self.settings.p7_qwen_local_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "video_url", "video_url": {"url": source_uri}},
                                {"type": "text", "text": _prompt(payload)},
                            ],
                        }
                    ],
                    "temperature": 0.2,
                    "max_tokens": 32768,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise ValueError("Local Qwen response did not contain choices")
        message = choices[0].get("message") or {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Local Qwen response did not contain final content")
        semantic = _parse_semantic(text)
        response_id = str(body.get("id") or "") or None
        return EpisodeUnderstandingProviderResult(semantic=semantic, remote_job_id=response_id)


def build_source_episode_understanding_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> SourceEpisodeUnderstandingProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoSeedSourceEpisodeUnderstandingProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_VL_LOCAL:
        return LocalQwenSourceEpisodeUnderstandingProvider(settings)
    raise AppError(
        "P7_PROVIDER_UNSUPPORTED",
        "当前 P7 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
