import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from arkruntime import Ark
from pydantic import BaseModel, SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.projects.enums import SourceUnderstandingProvider
from app.skills.professional import get_professional_skill
from app.source_resolution.schemas import (
    CharacterResolutionSemantic,
    PropResolutionSemantic,
    SceneResolutionSemantic,
    SpeakerResolutionSemantic,
)


P9_PROMPT_VERSION = "p9-source-resolution-v8"
P9_SCHEMA_VERSION = "1.0"
P9_SOURCE_TRUTH_CONTRACT = "full-episode-global-resolution-v1"
P9_MAX_OUTPUT_TOKENS = 65536
P9_SKILL_IDS = (
    "character-resolution",
    "speaker-attribution",
    "scene-resolution",
    "prop-resolution",
)


_SEMANTIC_MODELS: dict[str, type[BaseModel]] = {
    "character-resolution": CharacterResolutionSemantic,
    "speaker-attribution": SpeakerResolutionSemantic,
    "scene-resolution": SceneResolutionSemantic,
    "prop-resolution": PropResolutionSemantic,
}

_SKILL_ERROR_NAMES = {
    "character-resolution": "CHARACTER",
    "speaker-attribution": "SPEAKER",
    "scene-resolution": "SCENE",
    "prop-resolution": "PROP",
}

# Keep the request-level JSON Schema aligned with the Pydantic contract that parses the
# provider response afterwards. P9 v5 intentionally used a small allowlist inherited from
# older prompt-only schemas, but it dropped Pydantic string guards such as maxLength. That
# meant Ark could return output that satisfied the request schema but was then rejected by
# the server-side model (most visibly on verbose Prop reasons/evidence notes).
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
class ResolutionEpisodeVideo:
    source_path: Path
    source_filename: str
    mime_type: str
    episode_id: str
    episode_order: int
    duration_us: int
    source_asset_sha256: str


@dataclass(frozen=True)
class ProjectResolutionInput:
    episodes: tuple[ResolutionEpisodeVideo, ...]
    source_language: str | None
    source_bible: dict
    source_shot_facts: dict
    canonical_dialogue: list[dict]
    source_characters: dict | None = None


@dataclass(frozen=True)
class ResolutionProviderResult:
    semantic: BaseModel
    remote_job_id: str | None


class SourceResolutionProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self, professional_skill_id: str) -> dict: ...

    def analyze(self, professional_skill_id: str, payload: ProjectResolutionInput) -> ResolutionProviderResult: ...


def _clean_json_schema(value: Any) -> Any:
    """Retain only JSON-Schema keywords accepted by the provider contract.

    Unlike the pre-v6 helper, this deliberately preserves Pydantic string/collection/
    numeric constraints so the remote strict schema cannot be weaker than the local parser.
    Defaults and presentation-only metadata outside the allowlist remain omitted.
    """

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


def _source_reference_sets(payload: ProjectResolutionInput) -> dict[str, set[str]]:
    episodes = payload.source_shot_facts.get("episodes", [])
    shots = [shot for episode in episodes for shot in episode.get("shots", [])]
    episode_ids = {item.episode_id for item in payload.episodes}
    shot_ids = {str(shot["shot_anchor_id"]) for shot in shots}
    utterance_ids = {str(item["utterance_id"]) for item in payload.canonical_dialogue}
    character_candidate_ids = {
        str(item["id"])
        for shot in shots
        for item in shot.get("bindings", {}).get("characters", [])
    }
    scene_candidate_ids = {
        str(item["id"])
        for shot in shots
        for item in shot.get("bindings", {}).get("scenes", [])
    }
    prop_candidate_ids = {
        str(item["id"])
        for shot in shots
        for item in shot.get("bindings", {}).get("props", [])
    }
    visual_text_ids = {
        str(item)
        for shot in shots
        for item in shot.get("visual_text_evidence_ids", [])
    }
    staged_character_ids = {
        str(item["character_id"])
        for item in (payload.source_characters or {}).get("entities", [])
    }
    all_ids = (
        episode_ids
        | shot_ids
        | utterance_ids
        | character_candidate_ids
        | scene_candidate_ids
        | prop_candidate_ids
        | visual_text_ids
        | staged_character_ids
    )
    return {
        "all": all_ids,
        "episodes": episode_ids,
        "shots": shot_ids,
        "utterances": utterance_ids,
        "character_candidates": character_candidate_ids,
        "scene_candidates": scene_candidate_ids,
        "prop_candidates": prop_candidate_ids,
        "staged_characters": staged_character_ids,
    }


def _reference_token_maps(payload: ProjectResolutionInput) -> tuple[dict[str, str], dict[str, str]]:
    source_ids = sorted(_source_reference_sets(payload)["all"])
    source_to_token = {source_id: f"R{index:04d}" for index, source_id in enumerate(source_ids, 1)}
    return source_to_token, {token: source_id for source_id, token in source_to_token.items()}


def _coverage_contract(skill_id: str, payload: ProjectResolutionInput) -> list[dict[str, Any]]:
    episodes = payload.source_shot_facts.get("episodes", [])
    shots = [shot for episode in episodes for shot in episode.get("shots", [])]
    source_to_token, _token_to_source = _reference_token_maps(payload)
    if skill_id == "character-resolution":
        return [
            {
                "shot_anchor_id": source_to_token[str(shot["shot_anchor_id"])],
                "source_candidate_id": source_to_token[str(candidate["id"])],
            }
            for shot in shots
            for candidate in shot.get("bindings", {}).get("characters", [])
        ]
    if skill_id == "speaker-attribution":
        return [
            {"utterance_id": source_to_token[str(item["utterance_id"])]}
            for item in payload.canonical_dialogue
        ]
    if skill_id == "scene-resolution":
        return [
            {
                "shot_anchor_id": source_to_token[str(shot["shot_anchor_id"])],
                "source_candidate_ids": [
                    source_to_token[str(item["id"])]
                    for item in shot.get("bindings", {}).get("scenes", [])
                ],
            }
            for shot in shots
        ]
    if skill_id == "prop-resolution":
        return [
            {
                "shot_anchor_id": source_to_token[str(shot["shot_anchor_id"])],
                "source_candidate_id": source_to_token[str(candidate["id"])],
            }
            for shot in shots
            for candidate in shot.get("bindings", {}).get("props", [])
        ]
    return []


def _set_string_enum(schema: dict[str, Any], values: set[str]) -> None:
    if not values:
        return
    allowed = sorted(values)
    if schema.get("type") == "string":
        schema["enum"] = allowed
        return
    for branch in schema.get("anyOf", []):
        if branch.get("type") == "string":
            branch["enum"] = allowed


def _bind_schema_to_source_ids(
    schema: dict[str, Any],
    skill_id: str,
    payload: ProjectResolutionInput,
) -> None:
    coverage = _coverage_contract(skill_id, payload)
    refs = _source_reference_sets(payload)
    source_to_token, _token_to_source = _reference_token_maps(payload)

    def tokens(values: set[str]) -> set[str]:
        return {source_to_token[value] for value in values}

    definitions = schema.get("$defs", {})
    evidence = definitions.get("EvidenceRef", {}).get("properties", {})
    _set_string_enum(evidence.get("ref_id", {}), tokens(refs["all"]))
    _set_string_enum(evidence.get("episode_id", {}), tokens(refs["episodes"]))
    _set_string_enum(evidence.get("shot_anchor_id", {}), tokens(refs["shots"]))
    _set_string_enum(evidence.get("utterance_id", {}), tokens(refs["utterances"]))

    if skill_id == "character-resolution":
        item_schema = definitions.get("CharacterObservationSemantic", {}).get("properties", {})
        array_schema = schema.get("properties", {}).get("observations", {})
        _set_string_enum(item_schema.get("shot_anchor_id", {}), tokens(refs["shots"]))
        _set_string_enum(
            item_schema.get("source_candidate_id", {}),
            tokens(refs["character_candidates"]),
        )
    elif skill_id == "speaker-attribution":
        item_schema = definitions.get("SpeakerAttributionSemantic", {}).get("properties", {})
        array_schema = schema.get("properties", {}).get("attributions", {})
        _set_string_enum(item_schema.get("utterance_id", {}), tokens(refs["utterances"]))
        speaker_group = definitions.get("SpeakerGroupSemantic", {}).get("properties", {})
        _set_string_enum(speaker_group.get("character_id", {}), tokens(refs["staged_characters"]))
        _set_string_enum(
            speaker_group.get("source_candidate_character_ids", {}).get("items", {}),
            tokens(refs["character_candidates"]),
        )
    elif skill_id == "scene-resolution":
        item_schema = definitions.get("SceneAssignmentSemantic", {}).get("properties", {})
        array_schema = schema.get("properties", {}).get("assignments", {})
        _set_string_enum(item_schema.get("shot_anchor_id", {}), tokens(refs["shots"]))
        _set_string_enum(
            item_schema.get("source_candidate_ids", {}).get("items", {}),
            tokens(refs["scene_candidates"]),
        )
    elif skill_id == "prop-resolution":
        item_schema = definitions.get("PropObservationSemantic", {}).get("properties", {})
        array_schema = schema.get("properties", {}).get("observations", {})
        _set_string_enum(item_schema.get("shot_anchor_id", {}), tokens(refs["shots"]))
        _set_string_enum(item_schema.get("source_candidate_id", {}), tokens(refs["prop_candidates"]))
    else:
        return

    array_schema["minItems"] = len(coverage)
    array_schema["maxItems"] = len(coverage)


def _provider_json_schema(
    skill_id: str,
    payload: ProjectResolutionInput | None = None,
) -> dict[str, Any]:
    model = _SEMANTIC_MODELS.get(skill_id)
    if model is None:
        raise AppError("P9_SKILL_UNSUPPORTED", "未知 P9 Professional Skill", status_code=500)
    schema = _clean_json_schema(model.model_json_schema())

    def provider_only_statuses(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                provider_only_statuses(item)
            return
        if not isinstance(value, dict):
            return
        enum_values = value.get("enum")
        if isinstance(enum_values, list) and "MANUAL_CONFIRMED" in enum_values:
            value["enum"] = [item for item in enum_values if item != "MANUAL_CONFIRMED"]
        for nested in value.values():
            provider_only_statuses(nested)

    provider_only_statuses(schema)
    if payload is not None:
        _bind_schema_to_source_ids(schema, skill_id, payload)
    return schema


def _structured_text_config(
    skill_id: str,
    payload: ProjectResolutionInput | None = None,
) -> dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": f"p9_{skill_id.replace('-', '_')}",
            "schema": _provider_json_schema(skill_id, payload),
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
    raise ValueError("P9 provider response did not contain a JSON object")


def _response_error_code(skill_id: str, suffix: str) -> str:
    prefix = _SKILL_ERROR_NAMES.get(skill_id, "UNKNOWN")
    return f"P9_{prefix}_PROVIDER_RESPONSE_{suffix}"


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


def _parse_semantic(skill_id: str, text: str) -> BaseModel:
    model = _SEMANTIC_MODELS.get(skill_id)
    if model is None:
        raise AppError("P9_SKILL_UNSUPPORTED", "未知 P9 Professional Skill", status_code=500)
    try:
        return model.model_validate_json(_json_text(text))
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(
            _response_error_code(skill_id, "INVALID"),
            f"{skill_id} Provider 返回结果未通过 P9 数据契约校验（{_validation_hint(exc)}）",
            status_code=502,
            details={"professional_skill_id": skill_id, "error_type": type(exc).__name__},
        ) from exc


def _restore_reference_tokens(
    skill_id: str,
    semantic: BaseModel,
    payload: ProjectResolutionInput,
) -> BaseModel:
    _source_to_token, token_to_source = _reference_token_maps(payload)

    def restore(value: str | None) -> str | None:
        if value is None:
            return None
        restored = token_to_source.get(value)
        if restored is None:
            raise AppError(
                _response_error_code(skill_id, "INVALID"),
                f"{skill_id} Provider 返回未知 Source 引用令牌",
                status_code=502,
                details={"professional_skill_id": skill_id},
            )
        return restored

    def restore_groups(groups: list[Any]) -> list[Any]:
        restored_groups: list[Any] = []
        for group in groups:
            evidence_refs = [
                ref.model_copy(
                    update={
                        "ref_id": restore(ref.ref_id),
                        "episode_id": restore(ref.episode_id),
                        "shot_anchor_id": restore(ref.shot_anchor_id),
                        "utterance_id": restore(ref.utterance_id),
                    }
                )
                for ref in group.evidence_refs
            ]
            updates: dict[str, Any] = {"evidence_refs": evidence_refs}
            if hasattr(group, "character_id"):
                updates["character_id"] = restore(group.character_id)
            if hasattr(group, "source_candidate_character_ids"):
                updates["source_candidate_character_ids"] = [
                    restore(value) for value in group.source_candidate_character_ids
                ]
            restored_groups.append(group.model_copy(update=updates))
        return restored_groups

    if isinstance(semantic, CharacterResolutionSemantic):
        return semantic.model_copy(
            update={
                "groups": restore_groups(semantic.groups),
                "observations": [
                    item.model_copy(
                        update={
                            "shot_anchor_id": restore(item.shot_anchor_id),
                            "source_candidate_id": restore(item.source_candidate_id),
                        }
                    )
                    for item in semantic.observations
                ],
            }
        )
    if isinstance(semantic, SpeakerResolutionSemantic):
        return semantic.model_copy(
            update={
                "groups": restore_groups(semantic.groups),
                "attributions": [
                    item.model_copy(update={"utterance_id": restore(item.utterance_id)})
                    for item in semantic.attributions
                ],
            }
        )
    if isinstance(semantic, SceneResolutionSemantic):
        return semantic.model_copy(
            update={
                "groups": restore_groups(semantic.groups),
                "assignments": [
                    item.model_copy(
                        update={
                            "shot_anchor_id": restore(item.shot_anchor_id),
                            "source_candidate_ids": [restore(value) for value in item.source_candidate_ids],
                        }
                    )
                    for item in semantic.assignments
                ],
            }
        )
    if isinstance(semantic, PropResolutionSemantic):
        return semantic.model_copy(
            update={
                "groups": restore_groups(semantic.groups),
                "observations": [
                    item.model_copy(
                        update={
                            "shot_anchor_id": restore(item.shot_anchor_id),
                            "source_candidate_id": restore(item.source_candidate_id),
                        }
                    )
                    for item in semantic.observations
                ],
            }
        )
    raise AppError("P9_SKILL_UNSUPPORTED", "未知 P9 Professional Skill", status_code=500)


def _empty_response_error(skill_id: str) -> AppError:
    return AppError(
        _response_error_code(skill_id, "EMPTY"),
        f"{skill_id} Provider 未返回可用的结构化文本",
        status_code=502,
        details={"professional_skill_id": skill_id},
    )


def _prompt(skill_id: str, payload: ProjectResolutionInput) -> str:
    skill = get_professional_skill(skill_id)
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    episode_summary = [
        {
            "episode_id": item.episode_id,
            "episode_order": item.episode_order,
            "source_filename": item.source_filename,
            "duration_us": item.duration_us,
            "source_asset_sha256": item.source_asset_sha256,
        }
        for item in payload.episodes
    ]
    provider_schema = _provider_json_schema(skill_id, payload)
    coverage_contract = _coverage_contract(skill_id, payload)
    source_to_token, _token_to_source = _reference_token_maps(payload)
    reference_legend = {
        token: source_id
        for source_id, token in sorted(source_to_token.items(), key=lambda item: item[1])
    }
    return f"""你正在执行 AI Drama Studio P9 Professional Skill：{skill.name}（{skill.id}@{skill.version}）。
这是 Speaker / Character / Scene / Prop 最终归一阶段，不是 P8 逐镜拉片，也不是 P10 SourceVideoSnapshot。

最高事实规则：
1. 下面附带的每个完整 Episode 都是 Source Truth；必须直接观看完整 Episode，并跨 Shot、必要时跨 Episode 做全局判断。
2. CURRENT P7 SOURCE_BIBLE 和 CURRENT P8 SOURCE_SHOT_FACTS 只是候选与语义/逐镜输入，不得把 candidate 直接升级为最终 identity。
3. P5 Shot 时间只读；不得输出、修正或重新切 Shot。
4. P6 canonical dialogue/OCR 只读；不得重新听写、改写、重编号或覆盖。
5. UNKNOWN / UNRESOLVED 是正式允许结果；证据不足时不得为了填满字段强制 merge 或 attribution。
6. 同名不等于同一实体，相似外观也不等于同一实体。
7. 输出中的 Source 引用字段只能填写“Source 引用令牌表”里的短令牌，不得直接抄写长 Source ID，不得创造令牌；服务端会确定性还原为真实 ID。全集级外观连续性请把对应 Episode 的同一令牌同时填入 ref_id 与 episode_id，不得用自造的 appearance_consistency 标签充当 ref_id。
8. 不输出 Target 内容，不创建 Snapshot。
9. Provider 只能输出 RESOLVED、UNKNOWN 或 UNRESOLVED；MANUAL_CONFIRMED 仅由用户显式人工裁决产生，禁止输出。
10. 所有字符串长度必须遵守下方请求级 JSON Schema；尤其 reason / evidence note 不得超过 schema 的 maxLength。不要输出超长解释，把必要依据压缩到允许长度内。
11. 输出主数组必须与“强制覆盖清单”逐项一一对应；数量必须相同，所有引用令牌必须逐字复制，不得截断、改写、补造或遗漏。可以改变 group_key / resolution_status / reason，但不得改变清单中的 Source 引用字段。

Professional Skill rules:
{rules}

Episodes:
{json.dumps(episode_summary, ensure_ascii=False, separators=(",", ":"))}

CURRENT SOURCE_BIBLE:
{json.dumps(payload.source_bible, ensure_ascii=False, separators=(",", ":"))}

CURRENT SOURCE_SHOT_FACTS:
{json.dumps(payload.source_shot_facts, ensure_ascii=False, separators=(",", ":"))}

CURRENT canonical dialogue（P6 权威，只读）:
{json.dumps(payload.canonical_dialogue, ensure_ascii=False, separators=(",", ":"))}

CURRENT SOURCE_CHARACTERS（仅 speaker-attribution 使用；其他 skill 可为空）:
{json.dumps(payload.source_characters, ensure_ascii=False, separators=(",", ":")) if payload.source_characters is not None else "null"}

Source 引用令牌表（仅输出左侧短令牌，右侧真实 ID 只用于查找）:
{json.dumps(reference_legend, ensure_ascii=False, separators=(",", ":"))}

强制覆盖清单（输出主数组必须完整覆盖，引用令牌逐字复制）:
{json.dumps(coverage_contract, ensure_ascii=False, separators=(",", ":"))}

只输出一个符合下列 JSON Schema 的 object，不输出 Markdown、解释或思考过程：
{json.dumps(provider_schema, ensure_ascii=False, separators=(",", ":"))}
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
        raise ValueError("Ark response did not contain output_text")
    return "".join(chunks)


def _assert_ark_response_completed(skill_id: str, response: Any) -> None:
    status = str(getattr(response, "status", "") or "").lower()
    if status != "incomplete":
        return
    incomplete_details = getattr(response, "incomplete_details", None)
    reason = getattr(incomplete_details, "reason", None)
    if reason is None and isinstance(incomplete_details, dict):
        reason = incomplete_details.get("reason")
    raise AppError(
        _response_error_code(skill_id, "INCOMPLETE"),
        f"{skill_id} Provider 输出未完成（{str(reason or 'unknown')}）",
        status_code=502,
        details={"professional_skill_id": skill_id, "incomplete_reason": str(reason or "unknown")},
    )


class DoubaoSeedSourceResolutionProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("P9_PROVIDER_NOT_CONFIGURED", "火山引擎 P9 Provider 尚未配置", status_code=409)

    @property
    def _api_key(self) -> str:
        assert self.settings.p7_doubao_api_key is not None
        return self.settings.p7_doubao_api_key.get_secret_value()

    @property
    def video_fps(self) -> float:
        return min(10.0, max(4.0, float(self.settings.p7_doubao_video_fps)))

    def profile(self, professional_skill_id: str) -> dict:
        skill = get_professional_skill(professional_skill_id)
        return {
            "selection": SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API.value,
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "CLOUD_API",
            "base_url": self.settings.p7_doubao_base_url,
            "video_input": "ARK_FILES_API_ALL_FULL_EPISODES",
            "video_fps": self.video_fps,
            "structured_output": "STRICT_JSON_SCHEMA_PROMPT_PLUS_SERVER_VALIDATION",
            "reference_encoding": "REQUEST_SCOPED_SOURCE_TOKENS_V1",
            "max_output_tokens": P9_MAX_OUTPUT_TOKENS,
            "prompt_version": P9_PROMPT_VERSION,
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P9_SOURCE_TRUTH_CONTRACT,
        }

    def analyze(self, professional_skill_id: str, payload: ProjectResolutionInput) -> ResolutionProviderResult:
        client = Ark(
            api_key=self._api_key,
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        uploaded_ids: list[str] = []
        try:
            for episode in payload.episodes:
                with episode.source_path.open("rb") as stream:
                    uploaded = client.files.create(file=stream, purpose="user_data")
                file_id = str(getattr(uploaded, "id", "") or "")
                if not file_id:
                    raise ValueError("Ark file upload did not return a file id")
                uploaded_ids.append(file_id)
                client.files.wait_for_processing(file_id, max_wait_seconds=self.settings.p7_doubao_request_timeout_seconds)
            content: list[dict] = [
                {"type": "input_video", "file_id": file_id, "fps": self.video_fps}
                for file_id in uploaded_ids
            ]
            content.append({"type": "input_text", "text": _prompt(professional_skill_id, payload)})
            response = client.responses.create(
                model=self.model_name,
                input=[{"role": "user", "content": content}],
                thinking={"type": "enabled"},
                text=_structured_text_config(professional_skill_id, payload),
                max_output_tokens=P9_MAX_OUTPUT_TOKENS,
            )
            _assert_ark_response_completed(professional_skill_id, response)
            try:
                response_text = _ark_response_text(response)
            except ValueError as exc:
                raise _empty_response_error(professional_skill_id) from exc
            semantic = _restore_reference_tokens(
                professional_skill_id,
                _parse_semantic(professional_skill_id, response_text),
                payload,
            )
            response_id = str(getattr(response, "id", "") or "") or None
            return ResolutionProviderResult(semantic=semantic, remote_job_id=response_id)
        finally:
            for file_id in uploaded_ids:
                try:
                    client.files.delete(file_id)
                except Exception:
                    pass


class LocalQwenSourceResolutionProvider:
    provider_name = "qwen-local-vllm"

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

    def profile(self, professional_skill_id: str) -> dict:
        skill = get_professional_skill(professional_skill_id)
        return {
            "selection": self.selection.value,
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "LOCAL_OPENAI_COMPATIBLE",
            "base_url": self.base_url,
            "video_input": "VLLM_FILE_URL_ALL_FULL_EPISODES",
            "structured_output": "STRICT_JSON_SCHEMA_PROMPT_PLUS_SERVER_VALIDATION",
            "reference_encoding": "REQUEST_SCOPED_SOURCE_TOKENS_V1",
            "prompt_version": P9_PROMPT_VERSION,
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P9_SOURCE_TRUTH_CONTRACT,
        }

    def analyze(self, professional_skill_id: str, payload: ProjectResolutionInput) -> ResolutionProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None:
            key = self.api_key.get_secret_value().strip()
            if key:
                headers["Authorization"] = f"Bearer {key}"
        content: list[dict] = [
            {"type": "video_url", "video_url": {"url": item.source_path.resolve().as_uri()}}
            for item in payload.episodes
        ]
        content.append({"type": "text", "text": _prompt(professional_skill_id, payload)})
        with httpx.Client(timeout=httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0.1,
                    "max_tokens": 32768,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise _empty_response_error(professional_skill_id)
        text = (choices[0].get("message") or {}).get("content")
        if not isinstance(text, str) or not text.strip():
            raise _empty_response_error(professional_skill_id)
        return ResolutionProviderResult(
            semantic=_restore_reference_tokens(
                professional_skill_id,
                _parse_semantic(professional_skill_id, text),
                payload,
            ),
            remote_job_id=str(body.get("id") or "") or None,
        )


def build_source_resolution_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> SourceResolutionProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoSeedSourceResolutionProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenSourceResolutionProvider(
            settings,
            selection=selection,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        effective = SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL
        return LocalQwenSourceResolutionProvider(
            settings,
            selection=effective,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P9_PROVIDER_UNSUPPORTED",
        "当前 P9 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
