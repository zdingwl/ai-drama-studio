import json
from dataclasses import dataclass
from typing import Any

import httpx
from arkruntime import Ark

from app.core.errors import AppError
from app.skills.professional import get_professional_skill
from app.target_script.providers import (
    P12_MAX_OUTPUT_TOKENS,
    DoubaoTargetScriptProvider,
    LocalQwenTargetScriptProvider,
    TargetScriptProvider,
    _ark_response_text,
    _assert_ark_response_completed,
    _clean_json_schema,
    _json_text,
    _validation_hint,
)
from app.target_script.schemas import (
    P12_SKILL_ID,
    TargetScriptTimingRewriteSemantic,
)


@dataclass(frozen=True)
class TimingRewriteProviderInput:
    target_language: str
    target_region: str
    adaptation_plan: dict
    target_bible: dict
    dialogue_requests: list[dict]


@dataclass(frozen=True)
class TimingRewriteProviderResult:
    semantic: TargetScriptTimingRewriteSemantic
    remote_job_id: str | None = None


def _json_schema(payload: TimingRewriteProviderInput) -> dict[str, Any]:
    schema = _clean_json_schema(TargetScriptTimingRewriteSemantic.model_json_schema())
    expected_ids = [str(item["utterance_id"]) for item in payload.dialogue_requests]
    dialogue_schema = schema.get("properties", {}).get("dialogue", {})
    dialogue_schema["minItems"] = len(expected_ids)
    dialogue_schema["maxItems"] = len(expected_ids)
    utterance_id_schema = (
        schema.get("$defs", {})
        .get("ProviderTimingRewriteDialogue", {})
        .get("properties", {})
        .get("utterance_id", {})
    )
    utterance_id_schema["enum"] = expected_ids
    return schema


def _parse(text: str) -> TargetScriptTimingRewriteSemantic:
    try:
        return TargetScriptTimingRewriteSemantic.model_validate_json(_json_text(text))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "P12_TIMING_REWRITE_PROVIDER_RESPONSE_INVALID",
            f"P12 Timing Rewrite Provider 返回结果未通过数据契约校验（{_validation_hint(exc)}）",
            status_code=502,
            details={"error_type": type(exc).__name__},
        ) from exc


def _prompt(payload: TimingRewriteProviderInput) -> str:
    skill = get_professional_skill(P12_SKILL_ID)
    schema = _json_schema(payload)
    coverage = [{"utterance_id": str(item["utterance_id"])} for item in payload.dialogue_requests]
    return f"""你正在执行 AI Drama Studio P12 Professional Skill 的 Timing Rewrite revision：{skill.name}（{skill.id}@{skill.version}）。

这不是重新翻译整部剧。服务端已经用真实 TTS + ffprobe 证明下列目标对白严重超出 Source slot，且理论所需 duration factor 低于 0.80。你只能缩短列出的目标表达。

目标：
- target_language: {payload.target_language}
- target_region: {payload.target_region}

最高规则：
1. 只处理 dialogue_requests 中列出的 utterance_id，数量和顺序必须完全一致；禁止新增、遗漏、合并、拆分或重排。
2. source_text / translation_text / source timing / target_character_id 都是只读事实；不得重新 ASR、重新翻译 Source Truth 或改变剧情信息。
3. localization_text 与 final_target_dialogue 可以改写得更短、更口语、更适合目标地区，但必须保留核心语义、人物关系、冲突功能、称谓关系和人物口吻。
4. required_duration_factor 只是压缩强度参考；禁止承诺新文案一定 FIT。真实结果仍由后续 TTS + ffprobe + Timing 决定。
5. 不生成 Voice/TTS/Timing/Storyboard/Generation/Post 内容。
6. localization_notes 简短说明本次压缩策略；不要输出 schema 之外字段。
7. 只输出符合 JSON Schema 的单个 object，不输出 Markdown、解释或思考过程。

CURRENT ADAPTATION_PLAN：
{json.dumps(payload.adaptation_plan, ensure_ascii=False, separators=(",", ":"))}

CURRENT TARGET_BIBLE：
{json.dumps(payload.target_bible, ensure_ascii=False, separators=(",", ":"))}

需要定向缩短的对白（未列出的对白不会发送给你，也不得修改）：
{json.dumps(payload.dialogue_requests, ensure_ascii=False, separators=(",", ":"))}

强制覆盖清单：
{json.dumps(coverage, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


def rewrite_for_timing(
    provider: TargetScriptProvider,
    payload: TimingRewriteProviderInput,
) -> TimingRewriteProviderResult:
    if isinstance(provider, DoubaoTargetScriptProvider):
        client = Ark(
            api_key=provider._api_key,
            base_url=provider.settings.p7_doubao_base_url,
            timeout=provider.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=provider.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _prompt(payload)}]}],
            thinking={"type": "enabled"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "p12_target_script_timing_rewrite",
                    "schema": _json_schema(payload),
                    "strict": True,
                }
            },
            max_output_tokens=P12_MAX_OUTPUT_TOKENS,
        )
        _assert_ark_response_completed(response)
        return TimingRewriteProviderResult(
            semantic=_parse(_ark_response_text(response)),
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )

    if isinstance(provider, LocalQwenTargetScriptProvider):
        headers = {"Content-Type": "application/json"}
        if provider.api_key is not None and provider.api_key.get_secret_value().strip():
            headers["Authorization"] = f"Bearer {provider.api_key.get_secret_value()}"
        with httpx.Client(timeout=httpx.Timeout(provider.settings.p7_qwen_local_request_timeout_seconds)) as client:
            response = client.post(
                f"{provider.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": provider.model_name,
                    "messages": [{"role": "user", "content": _prompt(payload)}],
                    "temperature": 0.1,
                    "max_tokens": P12_MAX_OUTPUT_TOKENS,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise AppError("P12_PROVIDER_RESPONSE_EMPTY", "P12 Timing Rewrite Provider 未返回 choices", status_code=502)
        text = (choices[0].get("message") or {}).get("content")
        if not isinstance(text, str) or not text.strip():
            raise AppError("P12_PROVIDER_RESPONSE_EMPTY", "P12 Timing Rewrite Provider 未返回可用文本", status_code=502)
        return TimingRewriteProviderResult(
            semantic=_parse(text),
            remote_job_id=str(body.get("id") or "") or None,
        )

    raise AppError(
        "P12_TIMING_REWRITE_PROVIDER_UNSUPPORTED",
        "当前 P12 Provider 不支持 Timing Rewrite",
        status_code=422,
        details={"provider": provider.provider_name},
    )
