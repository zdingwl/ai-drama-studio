import json
import re
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


P12_MAX_OUTPUT_TOKENS = 65536

_JSON_SCHEMA_KEYS = {
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
    "uniqueItems",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minProperties",
    "maxProperties",
    "anyOf",
    "oneOf",
    "allOf",
    "properties",
    "additionalProperties",
    "required",
}


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


def _clean_json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_clean_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned: dict[str, Any] = {}
    for key, nested in value.items():
        if key not in _JSON_SCHEMA_KEYS:
            continue
        if key in {"properties", "$defs"}:
            cleaned[key] = {name: _clean_json_schema(schema) for name, schema in nested.items()}
        else:
            cleaned[key] = _clean_json_schema(nested)
    return cleaned


def _provider_json_schema(payload: TargetScriptProviderInput) -> dict[str, Any]:
    schema = _clean_json_schema(TargetScriptSemantic.model_json_schema())
    dialogue_schema = schema.get("properties", {}).get("dialogue", {})
    expected_ids = [str(item["utterance_id"]) for item in payload.canonical_dialogue_manifest]
    dialogue_schema["minItems"] = len(expected_ids)
    dialogue_schema["maxItems"] = len(expected_ids)

    utterance_id_schema = (
        schema.get("$defs", {})
        .get("ProviderLocalizedDialogue", {})
        .get("properties", {})
        .get("utterance_id", {})
    )
    if expected_ids:
        utterance_id_schema["enum"] = expected_ids
    return schema


def _structured_text_config(payload: TargetScriptProviderInput) -> dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": "p12_target_script_localization",
            "schema": _provider_json_schema(payload),
            "strict": True,
        }
    }


def _json_text(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    if value.startswith("{") and value.endswith("}"):
        return value
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("P12_PROVIDER_RESPONSE_INVALID", "P12 Provider 未返回 JSON object", status_code=502)


def _validation_hint(exc: Exception) -> str:
    errors_method = getattr(exc, "errors", None)
    if callable(errors_method):
        try:
            errors = errors_method(include_url=False, include_input=False)
        except TypeError:
            errors = errors_method()
        hints: list[str] = []
        for item in errors[:3]:
            loc = ".".join(str(part) for part in item.get("loc", ())) or "root"
            error_type = str(item.get("type") or "invalid")
            ctx = item.get("ctx") if isinstance(item, dict) else None
            safe_ctx: list[str] = []
            if isinstance(ctx, dict):
                for key in ("min_length", "max_length", "limit_value", "ge", "le"):
                    value = ctx.get(key)
                    if isinstance(value, (str, int, float, bool)):
                        safe_ctx.append(f"{key}={value}")
            suffix = f"[{','.join(safe_ctx)}]" if safe_ctx else ""
            hints.append(f"{loc}:{error_type}{suffix}")
        if hints:
            return ", ".join(hints)
    return type(exc).__name__


def _parse(text: str) -> TargetScriptSemantic:
    try:
        return TargetScriptSemantic.model_validate_json(_json_text(text))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "P12_PROVIDER_RESPONSE_INVALID",
            f"P12 Provider 返回结果未通过数据契约校验（{_validation_hint(exc)}）",
            status_code=502,
            details={"error_type": type(exc).__name__},
        ) from exc


def _prompt(payload: TargetScriptProviderInput) -> str:
    skill = get_professional_skill(P12_SKILL_ID)
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    schema = _provider_json_schema(payload)
    coverage = [
        {"utterance_id": str(item["utterance_id"])}
        for item in payload.canonical_dialogue_manifest
    ]
    return f"""你正在执行 AI Drama Studio P12 Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

这是 Target Script / Localization 阶段。你只能把服务端给出的 canonical Source Dialogue 转换成目标语言对白，不得重新猜 Source 台词。

目标：
- target_language: {payload.target_language}
- target_region: {payload.target_region}

最高规则：
1. canonical_dialogue_manifest 中的 utterance_id / source_text / timing 是只读 Source Truth；禁止 ASR、OCR、口型猜词、剧情补词或修正 source_text。
2. dialogue 必须与“强制覆盖清单”逐项一一完整覆盖，数量相同、顺序一致；utterance_id 必须逐字复制，不得遗漏、重复、创造、合并、拆分或截断。
3. translation_text 是直接语义翻译；localization_text 是结合 Target Bible / Adaptation Plan 的文化、称谓、语气和自然表达本土化；final_target_dialogue 是本阶段最终对白。
4. 不得为了“塞回原镜头”静默压缩对白。真实语音时长只属于后续 TTS / Timing。
5. 不得输出或推断 Target Voice、TTS、Actual Speech Duration、Timing Plan、Target Storyboard、Generation、QC、Selection 或 Post 信息。
6. 不得重排 Story Beat / Scene / Shot，不得修改 P11 preservation locks。
7. 所有字符串和数组长度必须遵守下方请求级 JSON Schema，不要输出 schema 之外的字段。
8. 只输出符合 JSON Schema 的单个 object，不输出 Markdown、解释或思考过程。

Professional Skill rules:
{rules}

CURRENT ADAPTATION_PLAN：
{json.dumps(payload.adaptation_plan, ensure_ascii=False, separators=(",", ":"))}

CURRENT TARGET_BIBLE：
{json.dumps(payload.target_bible, ensure_ascii=False, separators=(",", ":"))}

Canonical Source Dialogue manifest（source_* 字段全部只读）：
{json.dumps(payload.canonical_dialogue_manifest, ensure_ascii=False, separators=(",", ":"))}

强制覆盖清单（dialogue 必须按此顺序完整覆盖）：
{json.dumps(coverage, ensure_ascii=False, separators=(",", ":"))}

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


def _assert_ark_response_completed(response: Any) -> None:
    status = str(getattr(response, "status", "") or "").lower()
    if status != "incomplete":
        return
    details = getattr(response, "incomplete_details", None)
    reason = getattr(details, "reason", None) if details is not None else None
    if reason is None and isinstance(details, dict):
        reason = details.get("reason")
    raise AppError(
        "P12_PROVIDER_RESPONSE_INCOMPLETE",
        f"P12 Provider 输出未完成（{str(reason or 'unknown')}）",
        status_code=502,
        details={"incomplete_reason": str(reason or "unknown")},
    )


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
        profile["structured_output"] = "STRICT_JSON_SCHEMA_PROMPT_PLUS_SERVER_VALIDATION"
        profile["max_output_tokens"] = P12_MAX_OUTPUT_TOKENS
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
            text=_structured_text_config(payload),
            max_output_tokens=P12_MAX_OUTPUT_TOKENS,
        )
        _assert_ark_response_completed(response)
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
        profile["structured_output"] = "PROMPT_PLUS_SERVER_VALIDATION"
        profile["max_output_tokens"] = P12_MAX_OUTPUT_TOKENS
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
