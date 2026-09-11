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
from app.target_script.schemas import (
    P12_PROMPT_VERSION,
    P12_SCHEMA_VERSION,
    P12_SKILL_ID,
    P12_SOURCE_DIALOGUE_CONTRACT,
    P12_TARGET_CONTRACT,
    TargetScriptSemantic,
)


P12_MAX_OUTPUT_TOKENS = 32768


@dataclass(frozen=True)
class TargetScriptProviderInput:
    target_language: str
    target_region: str
    adaptation_plan: dict
    target_bible: dict
    canonical_dialogue_manifest: list[dict]


@dataclass(frozen=True)
class TargetScriptProviderResult:
    semantic: TargetScriptSemantic
    remote_job_id: str | None = None


class TargetScriptProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def localize(self, payload: TargetScriptProviderInput) -> TargetScriptProviderResult: ...


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
    raise AppError("P12_PROVIDER_RESPONSE_INVALID", "P12 Provider 未返回 JSON object", status_code=502)


def _parse(text: str) -> TargetScriptSemantic:
    try:
        return TargetScriptSemantic.model_validate_json(_json_text(text))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "P12_PROVIDER_RESPONSE_INVALID",
            f"P12 Provider 返回结果未通过数据契约校验（{type(exc).__name__}）",
            status_code=502,
        ) from exc


def _prompt(payload: TargetScriptProviderInput) -> str:
    skill = get_professional_skill(P12_SKILL_ID)
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    schema = TargetScriptSemantic.model_json_schema()
    return f"""你正在执行 AI Drama Studio P12 Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

这是 Target Script / Localization 阶段。你只能把服务端给出的 canonical Source Dialogue 转换成目标语言对白，不得重新猜 Source 台词。

目标：
- target_language: {payload.target_language}
- target_region: {payload.target_region}

最高规则：
1. canonical_dialogue_manifest 中的 utterance_id / source_text / timing 是只读 Source Truth；禁止 ASR、OCR、口型猜词、剧情补词或修正 source_text。
2. dialogue 必须与 manifest 中全部 utterance_id 一一完整覆盖，顺序一致；不得遗漏、重复、创造、合并或拆分 utterance。
3. translation_text 是直接语义翻译；localization_text 是结合 Target Bible / Adaptation Plan 的文化、称谓、语气和自然表达本土化；final_target_dialogue 是本阶段最终对白。
4. 不得为了“塞回原镜头”静默压缩对白。真实语音时长只属于后续 TTS / Timing。
5. 不得输出或推断 Target Voice、TTS、Actual Speech Duration、Timing Plan、Target Storyboard、Generation、QC、Selection 或 Post 信息。
6. 不得重排 Story Beat / Scene / Shot，不得修改 P11 preservation locks。
7. 只输出符合 JSON Schema 的单个 object，不输出 Markdown、解释或思考过程。

Professional Skill rules:
{rules}

CURRENT ADAPTATION_PLAN：
{json.dumps(payload.adaptation_plan, ensure_ascii=False, separators=(",", ":"))}

CURRENT TARGET_BIBLE：
{json.dumps(payload.target_bible, ensure_ascii=False, separators=(",", ":"))}

Canonical Source Dialogue manifest（source_* 字段全部只读）：
{json.dumps(payload.canonical_dialogue_manifest, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
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
        parts = getattr(item, "content", None) if not isinstance(item, dict) else item.get("content")
        for part in parts or []:
            part_type = getattr(part, "type", None) if not isinstance(part, dict) else part.get("type")
            if part_type != "output_text":
                continue
            text = getattr(part, "text", None) if not isinstance(part, dict) else part.get("text")
            if text:
                chunks.append(str(text))
    if not chunks:
        raise AppError("P12_PROVIDER_RESPONSE_EMPTY", "P12 Provider 未返回可用文本", status_code=502)
    return "".join(chunks)


def _profile(selection: SourceUnderstandingProvider, provider: str, model: str, mode: str) -> dict:
    skill = get_professional_skill(P12_SKILL_ID)
    return {
        "selection": selection.value,
        "provider": provider,
        "model": model,
        "mode": mode,
        "prompt_version": P12_PROMPT_VERSION,
        "schema_version": P12_SCHEMA_VERSION,
        "target_contract": P12_TARGET_CONTRACT,
        "source_dialogue_contract": P12_SOURCE_DIALOGUE_CONTRACT,
        "professional_skill_id": skill.id,
        "professional_skill_version": skill.version,
    }


class DoubaoTargetScriptProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("P12_PROVIDER_NOT_CONFIGURED", "火山引擎 P12 Provider 尚未配置", status_code=409)

    @property
    def _api_key(self) -> str:
        assert self.settings.p7_doubao_api_key is not None
        return self.settings.p7_doubao_api_key.get_secret_value()

    def profile(self) -> dict:
        profile = _profile(
            SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API,
            self.provider_name,
            self.model_name,
            "CLOUD_API_TEXT_ONLY",
        )
        profile["base_url"] = self.settings.p7_doubao_base_url
        profile["structured_output"] = "PYDANTIC_JSON_SCHEMA_PLUS_SERVER_VALIDATION"
        return profile

    def localize(self, payload: TargetScriptProviderInput) -> TargetScriptProviderResult:
        client = Ark(
            api_key=self._api_key,
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _prompt(payload)}]}],
            thinking={"type": "enabled"},
            max_output_tokens=P12_MAX_OUTPUT_TOKENS,
        )
        status = str(getattr(response, "status", "") or "").lower()
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None) if details is not None else None
            raise AppError(
                "P12_PROVIDER_RESPONSE_INCOMPLETE",
                f"P12 Provider 输出未完成（{str(reason or 'unknown')}）",
                status_code=502,
            )
        return TargetScriptProviderResult(
            semantic=_parse(_ark_response_text(response)),
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


class LocalQwenTargetScriptProvider:
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

    def localize(self, payload: TargetScriptProviderInput) -> TargetScriptProviderResult:
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
                    "max_tokens": P12_MAX_OUTPUT_TOKENS,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise AppError("P12_PROVIDER_RESPONSE_EMPTY", "P12 Provider 未返回 choices", status_code=502)
        text = (choices[0].get("message") or {}).get("content")
        if not isinstance(text, str) or not text.strip():
            raise AppError("P12_PROVIDER_RESPONSE_EMPTY", "P12 Provider 未返回可用文本", status_code=502)
        return TargetScriptProviderResult(
            semantic=_parse(text),
            remote_job_id=str(body.get("id") or "") or None,
        )


def build_target_script_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> TargetScriptProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoTargetScriptProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenTargetScriptProvider(
            settings,
            selection=selection,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        effective = SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL
        return LocalQwenTargetScriptProvider(
            settings,
            selection=effective,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P12_PROVIDER_UNSUPPORTED",
        "当前 P12 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
