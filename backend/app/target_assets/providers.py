import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from arkruntime import Ark
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.projects.enums import SourceUnderstandingProvider
from app.skills.professional import get_professional_skill
from app.target_assets.schemas import (
    P13_PROMPT_VERSION,
    P13_SCHEMA_VERSION,
    P13_SKILL_ID,
    P13_TARGET_CONTRACT,
    TargetAssetsProviderInput,
    TargetAssetsSemantic,
)


P13_MAX_OUTPUT_TOKENS = 32768


@dataclass(frozen=True)
class TargetAssetsSpecProviderResult:
    semantic: TargetAssetsSemantic
    remote_job_id: str | None = None


class TargetAssetsSpecProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def design(self, payload: TargetAssetsProviderInput) -> TargetAssetsSpecProviderResult: ...


@dataclass(frozen=True)
class TargetAssetImageRequest:
    target_asset_id: str
    asset_kind: str
    prompt: str


@dataclass(frozen=True)
class TargetAssetImageProviderResult:
    image_bytes: bytes
    media_type: str
    remote_job_id: str | None = None


class TargetAssetImageProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def generate(self, payload: TargetAssetImageRequest) -> TargetAssetImageProviderResult: ...


def _json_text(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    if value.startswith("{") and value.endswith("}"):
        return value
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("P13_PROVIDER_RESPONSE_INVALID", "P13 Provider 未返回 JSON object", status_code=502)


def _parse_semantic(text: str) -> TargetAssetsSemantic:
    try:
        return TargetAssetsSemantic.model_validate_json(_json_text(text))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "P13_PROVIDER_RESPONSE_INVALID",
            f"P13 Provider 返回结果未通过数据契约校验（{type(exc).__name__}）",
            status_code=502,
        ) from exc


def _prompt(payload: TargetAssetsProviderInput) -> str:
    skill = get_professional_skill(P13_SKILL_ID)
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    schema = TargetAssetsSemantic.model_json_schema()
    return f"""你正在执行 AI Drama Studio P13 Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

这是 Replica Target Assets 的视觉规格阶段。Target Bible 是 semantic truth；你只能做 visual realization。

最高规则：
1. 只处理下方输入里出现的 Target Character / Scene / Prop，必须逐字返回每个 target_*_id，不能遗漏、重复、增补或修改 ID。
2. 不得改变人物故事功能、人物身份、场景功能、关键道具功能、Target World、display_name 或 P11 已确定的语义字段。
3. 你的任务是把视觉身份具体化到足以跨镜复用：人物脸/发型/体型/服装与标志特征，场景空间/布局/材质/固定 landmark/光线，道具形态/材质/颜色/尺度/功能特征。
4. continuity_constraints 必须服务跨镜一致性；negative_constraints 必须写清不能漂移的视觉项。
5. generation_guidance 是 reference sheet 和后续视觉生成指导，不得加入 Shot 编号、镜头 timing、对白、Storyboard、Generation Segment、TTS 或视频生成任务。
6. 不得输出 target_asset_id、Artifact ID、数据库 ID、revision、CURRENT/STALE；这些由服务端确定。
7. 只输出符合 JSON Schema 的单个 object，不输出 Markdown、解释或思考过程。

Professional Skill rules:
{rules}

目标语言/地区：{payload.target_language} / {payload.target_region}
Target World:
{json.dumps(payload.target_world, ensure_ascii=False, separators=(",", ":"))}
Visual Style:
{payload.visual_style}
Global continuity rules:
{json.dumps(payload.global_continuity_rules, ensure_ascii=False, separators=(",", ":"))}

Characters（只处理这些 ID）：
{json.dumps(payload.characters, ensure_ascii=False, separators=(",", ":"))}

Scenes（只处理这些 ID）：
{json.dumps(payload.scenes, ensure_ascii=False, separators=(",", ":"))}

Props（只处理这些 ID）：
{json.dumps(payload.props, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


def _profile(selection: SourceUnderstandingProvider, provider: str, model: str, mode: str) -> dict:
    skill = get_professional_skill(P13_SKILL_ID)
    return {
        "selection": selection.value,
        "provider": provider,
        "model": model,
        "mode": mode,
        "prompt_version": P13_PROMPT_VERSION,
        "schema_version": P13_SCHEMA_VERSION,
        "asset_contract": P13_TARGET_CONTRACT,
        "professional_skill_id": skill.id,
        "professional_skill_version": skill.version,
    }


def _ark_response_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None) if not isinstance(item, dict) else item.get("type")
        if item_type != "message":
            continue
        parts = getattr(item, "content", None) if not isinstance(item, dict) else item.get("content")
        for part in parts or []:
            part_type = getattr(part, "type", None) if not isinstance(part, dict) else part.get("type")
            if part_type != "output_text":
                continue
            text = getattr(part, "text", None) if not isinstance(part, dict) else part.get("text")
            if text:
                chunks.append(str(text))
    if not chunks:
        raise AppError("P13_PROVIDER_RESPONSE_EMPTY", "P13 Provider 未返回可用文本", status_code=502)
    return "".join(chunks)


class DoubaoTargetAssetsSpecProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("P13_SPEC_PROVIDER_NOT_CONFIGURED", "火山引擎 P13 Visual Spec Provider 尚未配置", status_code=409)

    def profile(self) -> dict:
        profile = _profile(
            SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API,
            self.provider_name,
            self.model_name,
            "CLOUD_API_TEXT_ONLY",
        )
        profile["base_url"] = self.settings.p7_doubao_base_url
        return profile

    def design(self, payload: TargetAssetsProviderInput) -> TargetAssetsSpecProviderResult:
        assert self.settings.p7_doubao_api_key is not None
        client = Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _prompt(payload)}]}],
            thinking={"type": "enabled"},
            max_output_tokens=P13_MAX_OUTPUT_TOKENS,
        )
        if str(getattr(response, "status", "") or "").lower() == "incomplete":
            raise AppError("P13_PROVIDER_RESPONSE_INCOMPLETE", "P13 Provider 输出未完成", status_code=502)
        return TargetAssetsSpecProviderResult(
            semantic=_parse_semantic(_ark_response_text(response)),
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


class LocalQwenTargetAssetsSpecProvider:
    provider_name = "local-vllm"

    def __init__(
        self,
        settings: Settings,
        *,
        selection: SourceUnderstandingProvider,
        model_name: str,
        base_url: str,
        api_key: SecretStr | None,
    ):
        self.settings = settings
        self.selection = selection
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key

    def profile(self) -> dict:
        profile = _profile(self.selection, self.provider_name, self.model_name, "LOCAL_VLLM_TEXT_ONLY")
        profile["base_url"] = self.base_url
        return profile

    def design(self, payload: TargetAssetsProviderInput) -> TargetAssetsSpecProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        with httpx.Client(timeout=httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": _prompt(payload)}],
                    "temperature": 0.2,
                    "max_tokens": P13_MAX_OUTPUT_TOKENS,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") if choices else None)
        if not isinstance(text, str) or not text.strip():
            raise AppError("P13_PROVIDER_RESPONSE_EMPTY", "P13 Provider 未返回可用文本", status_code=502)
        return TargetAssetsSpecProviderResult(
            semantic=_parse_semantic(text),
            remote_job_id=str(body.get("id") or "") or None,
        )


def build_target_assets_spec_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> TargetAssetsSpecProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoTargetAssetsSpecProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenTargetAssetsSpecProvider(
            settings,
            selection=selection,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        effective = SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL
        return LocalQwenTargetAssetsSpecProvider(
            settings,
            selection=effective,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P13_SPEC_PROVIDER_UNSUPPORTED",
        "当前 P13 Visual Spec Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )


class OpenAICompatibleTargetAssetImageProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider_name = settings.p13_image_provider.strip() or "openai-compatible-image"
        self.model_name = settings.p13_image_model.strip()
        self.base_url = settings.p13_image_base_url.strip()
        if not self.base_url or not self.model_name:
            raise AppError(
                "P13_IMAGE_PROVIDER_NOT_CONFIGURED",
                "P13 图片 Provider 尚未配置，不能生成或伪造正式 Target Assets",
                status_code=409,
            )

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "OPENAI_COMPATIBLE_IMAGE_B64",
            "base_url": self.base_url,
            "size": self.settings.p13_image_size,
            "prompt_version": P13_PROMPT_VERSION,
            "asset_contract": P13_TARGET_CONTRACT,
        }

    def generate(self, payload: TargetAssetImageRequest) -> TargetAssetImageProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.settings.p13_image_api_key is not None and self.settings.p13_image_api_key.get_secret_value().strip():
            headers["Authorization"] = f"Bearer {self.settings.p13_image_api_key.get_secret_value()}"
        with httpx.Client(timeout=httpx.Timeout(self.settings.p13_image_request_timeout_seconds)) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/images/generations",
                headers=headers,
                json={
                    "model": self.model_name,
                    "prompt": payload.prompt,
                    "n": 1,
                    "size": self.settings.p13_image_size,
                    "response_format": "b64_json",
                },
            )
            response.raise_for_status()
            body = response.json()
        data = body.get("data") or []
        encoded = data[0].get("b64_json") if data and isinstance(data[0], dict) else None
        if not isinstance(encoded, str) or not encoded.strip():
            raise AppError(
                "P13_IMAGE_PROVIDER_RESPONSE_INVALID",
                "P13 图片 Provider 未返回 b64_json image bytes",
                status_code=502,
            )
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise AppError(
                "P13_IMAGE_PROVIDER_RESPONSE_INVALID",
                "P13 图片 Provider 返回的 base64 无法解码",
                status_code=502,
            ) from exc
        if not image_bytes:
            raise AppError("P13_IMAGE_PROVIDER_RESPONSE_EMPTY", "P13 图片 Provider 返回空图片", status_code=502)
        remote_id = str(body.get("id") or body.get("created") or "") or None
        return TargetAssetImageProviderResult(
            image_bytes=image_bytes,
            media_type="image/png",
            remote_job_id=remote_id,
        )


def build_target_asset_image_provider(settings: Settings) -> TargetAssetImageProvider:
    if (settings.p13_image_provider.strip() or "openai-compatible-image") != "openai-compatible-image":
        raise AppError(
            "P13_IMAGE_PROVIDER_UNSUPPORTED",
            "当前 P13 图片 Provider adapter 未实现",
            status_code=422,
            details={"provider": settings.p13_image_provider},
        )
    return OpenAICompatibleTargetAssetImageProvider(settings)
