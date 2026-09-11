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
from app.target_assets.schemas import (
    P13_ENTITY_BINDING_CONTRACT,
    P13_PROMPT_VERSION,
    P13_REVIEW_CONTRACT,
    P13_SCHEMA_VERSION,
    P13_SKILL_ID,
    P13_TARGET_ASSET_CONTRACT,
    TargetAssetsSemantic,
)


P13_MAX_OUTPUT_TOKENS = 65536
P13_REVIEW_LANGUAGE = "zh-CN"
P13_REVIEW_LANGUAGE_CONTRACT = "zh-cn-human-review-asset-local-visual-v2"

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
class TargetAssetsProviderInput:
    target_language: str
    target_region: str
    target_bible: dict
    entity_manifest: dict[str, list[dict[str, str]]]


@dataclass(frozen=True)
class TargetAssetsProviderResult:
    semantic: TargetAssetsSemantic
    remote_job_id: str | None = None


class TargetAssetsProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def design(self, payload: TargetAssetsProviderInput) -> TargetAssetsProviderResult: ...


def _project_records(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projected: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        projected.append({key: raw[key] for key in keys if key in raw})
    return projected


def _target_bible_visual_view(target_bible: dict[str, Any]) -> dict[str, Any]:
    """Expose only Target Bible fields needed for P13 visual realization.

    The complete TARGET_BIBLE Artifact remains the sole hard input, lineage anchor and
    generation fingerprint. This projection deliberately omits global story/dialogue
    text that the real-project review showed could leak into every review-facing asset
    packet. Entity-level visual continuity is retained as an upstream guardrail, not as
    text to copy verbatim.
    """

    return {
        "schema_version": target_bible.get("schema_version"),
        "target_language": target_bible.get("target_language"),
        "target_region": target_bible.get("target_region"),
        "target_world": target_bible.get("target_world"),
        "visual_style": target_bible.get("visual_style"),
        "characters": _project_records(
            target_bible.get("characters"),
            (
                "target_character_id",
                "display_name",
                "localized_identity",
                "appearance_direction",
                "continuity_rules",
            ),
        ),
        "scenes": _project_records(
            target_bible.get("scenes"),
            (
                "target_scene_id",
                "display_name",
                "localized_setting",
                "visual_direction",
                "continuity_rules",
            ),
        ),
        "props": _project_records(
            target_bible.get("props"),
            (
                "target_prop_id",
                "display_name",
                "localized_form",
                "continuity_rules",
            ),
        ),
    }


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


def _set_id_enum(schema: dict[str, Any], definition: str, field: str, values: list[str]) -> None:
    field_schema = schema.get("$defs", {}).get(definition, {}).get("properties", {}).get(field, {})
    if values:
        field_schema["enum"] = values


def _provider_json_schema(payload: TargetAssetsProviderInput) -> dict[str, Any]:
    schema = _clean_json_schema(TargetAssetsSemantic.model_json_schema())
    mappings = (
        ("characters", "ProviderCharacterAssetSemantic", "target_character_id", "target_character_id"),
        ("scenes", "ProviderSceneAssetSemantic", "target_scene_id", "target_scene_id"),
        ("props", "ProviderPropAssetSemantic", "target_prop_id", "target_prop_id"),
    )
    for collection, definition, field, manifest_field in mappings:
        values = [str(item[manifest_field]) for item in payload.entity_manifest.get(collection, [])]
        collection_schema = schema.get("properties", {}).get(collection, {})
        collection_schema["minItems"] = len(values)
        collection_schema["maxItems"] = len(values)
        _set_id_enum(schema, definition, field, values)
    return schema


def _structured_text_config(payload: TargetAssetsProviderInput) -> dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": "p13_replica_target_assets",
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
    raise AppError("P13_PROVIDER_RESPONSE_INVALID", "P13 Provider 未返回 JSON object", status_code=502)


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
            hints.append(f"{loc}:{error_type}")
        if hints:
            return ", ".join(hints)
    return type(exc).__name__


def _flatten_review_text(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_review_text(item))
        return result
    return []


def _review_text_groups(semantic: TargetAssetsSemantic) -> list[tuple[str, str, list[str]]]:
    groups: list[tuple[str, str, list[str]]] = []
    for item in semantic.characters:
        groups.append(
            (
                "CHARACTER",
                item.target_character_id,
                _flatten_review_text(
                    [
                        item.demographic_direction,
                        item.face_direction,
                        item.hair_direction,
                        item.body_direction,
                        item.wardrobe_baseline,
                        item.signature_visual_features,
                        item.continuity_constraints,
                        item.generation_guidance,
                        item.negative_constraints,
                    ]
                ),
            )
        )
    for item in semantic.scenes:
        groups.append(
            (
                "SCENE",
                item.target_scene_id,
                _flatten_review_text(
                    [
                        item.layout,
                        item.architecture_style,
                        item.interior_exterior_style,
                        item.materials_palette,
                        item.fixed_landmarks,
                        item.lighting_baseline,
                        item.time_of_day_baseline,
                        item.continuity_constraints,
                        item.generation_guidance,
                        item.negative_constraints,
                    ]
                ),
            )
        )
    for item in semantic.props:
        groups.append(
            (
                "PROP",
                item.target_prop_id,
                _flatten_review_text(
                    [
                        item.visual_form,
                        item.materials,
                        item.color_palette,
                        item.scale_reference,
                        item.signature_visual_features,
                        item.continuity_constraints,
                        item.generation_guidance,
                        item.negative_constraints,
                    ]
                ),
            )
        )
    return groups


def _assert_review_language(semantic: TargetAssetsSemantic) -> None:
    invalid: list[dict[str, Any]] = []
    for asset_type, target_entity_id, values in _review_text_groups(semantic):
        joined = "\n".join(values)
        cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", joined))
        latin_count = len(re.findall(r"[A-Za-z]", joined))
        # Chinese review prose is intentionally allowed to contain target-region proper nouns,
        # brands, model names and currency. Reject only English-dominant review packets.
        if cjk_count < 8 or (latin_count > 80 and cjk_count * 3 < latin_count):
            invalid.append(
                {
                    "asset_type": asset_type,
                    "target_entity_id": target_entity_id,
                    "cjk_count": cjk_count,
                    "latin_count": latin_count,
                }
            )
    if invalid:
        raise AppError(
            "P13_PROVIDER_REVIEW_LANGUAGE_INVALID",
            "目标资产审核说明必须以简体中文为主；人物名、地名、品牌、型号和金额可保留目标地区写法",
            status_code=502,
            details={
                "review_language": P13_REVIEW_LANGUAGE,
                "invalid_entities": invalid[:20],
            },
        )


def _parse(text: str) -> TargetAssetsSemantic:
    try:
        semantic = TargetAssetsSemantic.model_validate_json(_json_text(text))
        _assert_review_language(semantic)
        return semantic
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "P13_PROVIDER_RESPONSE_INVALID",
            f"P13 Provider 返回结果未通过数据契约校验（{_validation_hint(exc)}）",
            status_code=502,
            details={"error_type": type(exc).__name__},
        ) from exc


def _prompt(payload: TargetAssetsProviderInput) -> str:
    skill = get_professional_skill(P13_SKILL_ID)
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    schema = _provider_json_schema(payload)
    visual_bible = _target_bible_visual_view(payload.target_bible)
    return f"""你正在执行 AI Drama Studio P13 Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

这是 Target Assets / 目标资产阶段。Target Bible 是不可改写的 semantic truth；你只负责把已有 Target Character / Scene / Prop 具体化为跨镜稳定的视觉身份约束。

目标：
- target_language: {payload.target_language}
- target_region: {payload.target_region}
- review_language: {P13_REVIEW_LANGUAGE}

语言硬规则：
- target_language 是未来目标受众成品语言，不是本次审核说明语言。
- 所有供中国用户审核的视觉设计正文必须以简体中文表达，包括人物外形/服装/特征/连续性/生成指导/避免项，场景布局/风格/材质/地标/光照/时间基线/连续性，及道具形态/材质/颜色/尺度/特征/连续性。
- Lila Xu、Jake Miller、Austin、HEB、iPhone、$19.99 等目标地区人物名、地名、品牌、型号、货币和专有名词可以保留原文；解释这些实体的句子仍使用中文。
- generation_guidance 在 P13 是给用户审核的视觉设计指导，不是最终 image/video execution prompt。未来真正生成时由 Generation Adapter 再按模型需要整理英文或其他模型优化 prompt；本阶段不得提前进入 P14。
- 不得因为 target_language=en-US 就把本次审核正文整体输出为英文。

视觉资产作用域硬规则：
- continuity_constraints / generation_guidance / negative_constraints 只能描述当前人物、场景或道具的视觉身份稳定性；不得复制或改写 Target Bible 中的故事主线、Story Beat、镜头顺序、对白、节奏、Cliffhanger、人物关系等全局叙事锁。
- wardrobe_baseline 是人物基础视觉身份，不是逐 Scene / 逐 Shot 换装计划。除非 CURRENT TARGET_BIBLE 明确给出已确认的服装 variation，否则不得自行列出“场景 1/2/3 穿什么”或按剧情段落发明换装。
- time_of_day_baseline 是场景视觉基线，不是剧情时间轴。不得根据 Scene 顺序、闪回或情绪自行推断“深夜、次日上午、若干小时后”等故事时间变化；若 Target Bible 没有明确时段，只描述不依赖虚构剧情时间的稳定光照/环境基线，并说明具体时段由后续 Storyboard/Shot context 决定。
- P13 不负责复述 preservation locks。上游故事/镜头保留规则继续属于 Target Bible 与后续 production planning，不应重复塞进每个 Target Asset packet。

最高规则：
1. 只能读取 CURRENT TARGET_BIBLE；不得要求或推断 SOURCE_VIDEO_SNAPSHOT、ADAPTATION_PLAN、TARGET_SCRIPT 中的新事实。
2. characters / scenes / props 必须按 entity_manifest 的顺序逐项完整覆盖；target_*_id 必须逐字复制，不能遗漏、重复、创造、合并或拆分。
3. 下方只提供 CURRENT TARGET_BIBLE 的 P13 visual projection。完整 Target Bible Artifact 仍是唯一硬输入、lineage 与 fingerprint，但全局故事 / 对白 / preservation 文本不会重复提供给本阶段。visual projection 中的 display_name、localized_identity / localized_setting / localized_form、appearance / visual direction、entity continuity guardrail 与 visual style 是语义边界；可以具体化视觉表现，但不能改变人物故事身份、场景功能或关键道具功能，也不要逐字复制 guardrail。
4. 重点是跨 Shot 一致性：人物脸/发型/体态/服装基线、场景 layout/landmark/材质/光照基线、道具 form/material/color/scale 必须能稳定复用。
5. 不输出正式 target_asset_id、Artifact id、revision、fingerprint、CURRENT/STALE、图片 URI 或媒体 sha256；这些由服务端所有。
6. 当前 Provider 是 text-only。不得声称生成了图片，不得伪造 reference media。
7. 不输出 Target Voice、TTS、Timing、Target Storyboard、GenerationSegment、Video Generation、QC、Selection、Lip Sync 或 Post 信息。
8. 只输出符合请求级 JSON Schema 的单个 object，不输出 Markdown、解释或思考过程。

Professional Skill rules:
{rules}

Target entity manifest（必须按顺序完整覆盖）：
{json.dumps(payload.entity_manifest, ensure_ascii=False, separators=(",", ":"))}

CURRENT TARGET_BIBLE — P13 visual projection：
{json.dumps(visual_bible, ensure_ascii=False, separators=(",", ":"))}

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
        raise AppError("P13_PROVIDER_RESPONSE_EMPTY", "P13 Provider 未返回可用文本", status_code=502)
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
        "P13_PROVIDER_RESPONSE_INCOMPLETE",
        f"P13 Provider 输出未完成（{str(reason or 'unknown')}）",
        status_code=502,
        details={"incomplete_reason": str(reason or "unknown")},
    )


def _profile(selection: SourceUnderstandingProvider, provider: str, model: str, mode: str) -> dict:
    skill = get_professional_skill(P13_SKILL_ID)
    return {
        "selection": selection.value,
        "provider": provider,
        "model": model,
        "mode": mode,
        "prompt_version": P13_PROMPT_VERSION,
        "schema_version": P13_SCHEMA_VERSION,
        "target_asset_contract": P13_TARGET_ASSET_CONTRACT,
        "entity_binding_contract": P13_ENTITY_BINDING_CONTRACT,
        "review_contract": P13_REVIEW_CONTRACT,
        "review_language": P13_REVIEW_LANGUAGE,
        "review_language_contract": P13_REVIEW_LANGUAGE_CONTRACT,
        "professional_skill_id": skill.id,
        "professional_skill_version": skill.version,
        "reference_media_generation": "NOT_CONFIGURED",
    }


class DoubaoTargetAssetsProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("P13_PROVIDER_NOT_CONFIGURED", "火山引擎 P13 Provider 尚未配置", status_code=409)

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
        profile["structured_output"] = "STRICT_JSON_SCHEMA_PLUS_SERVER_VALIDATION"
        profile["max_output_tokens"] = P13_MAX_OUTPUT_TOKENS
        return profile

    def design(self, payload: TargetAssetsProviderInput) -> TargetAssetsProviderResult:
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
            max_output_tokens=P13_MAX_OUTPUT_TOKENS,
        )
        _assert_ark_response_completed(response)
        return TargetAssetsProviderResult(
            semantic=_parse(_ark_response_text(response)),
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


class LocalQwenTargetAssetsProvider:
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
        profile["max_output_tokens"] = P13_MAX_OUTPUT_TOKENS
        return profile

    def design(self, payload: TargetAssetsProviderInput) -> TargetAssetsProviderResult:
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
        if not choices:
            raise AppError("P13_PROVIDER_RESPONSE_EMPTY", "P13 Provider 未返回 choices", status_code=502)
        text = (choices[0].get("message") or {}).get("content")
        if not isinstance(text, str) or not text.strip():
            raise AppError("P13_PROVIDER_RESPONSE_EMPTY", "P13 Provider 未返回可用文本", status_code=502)
        return TargetAssetsProviderResult(
            semantic=_parse(text),
            remote_job_id=str(body.get("id") or "") or None,
        )


def build_target_assets_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> TargetAssetsProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoTargetAssetsProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenTargetAssetsProvider(
            settings,
            selection=selection,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        effective = SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL
        return LocalQwenTargetAssetsProvider(
            settings,
            selection=effective,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P13_PROVIDER_UNSUPPORTED",
        "当前 P13 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
