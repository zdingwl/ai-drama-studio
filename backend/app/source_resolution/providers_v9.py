"""P9 v9 Provider-wire correction for Source-owned Prop observation coverage.

P9's published typed Artifact contract remains unchanged.  This adapter narrows only the
Provider-facing Prop wire schema so the model cannot rewrite the authoritative P8
``(shot_anchor_id, source_candidate_id)`` pairs.

The v8 token contract constrained each reference field independently.  A model could therefore
return a valid Shot token together with a valid Prop token that were never bound to each other in
CURRENT P8.  v9 moves those immutable Source pairs into fixed JSON object keys owned by the
server.  The Provider supplies only the semantic decision for each key; this adapter reconstructs
the canonical ``PropObservationSemantic`` rows before the existing token restoration and
``_compose_props`` exact-set guard run.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from pydantic import BaseModel

from app.core.errors import AppError
from app.source_resolution import providers as _base
from app.source_resolution.schemas import PropResolutionSemantic


P9_PROMPT_VERSION = "p9-source-resolution-v9"
P9_PROP_WIRE_CONTRACT = "source-owned-prop-observation-keys-v1"
_PROP_SKILL_ID = "prop-resolution"
_PROP_KEY_SEPARATOR = "__"
_PROP_SOURCE_FIELDS = {"shot_anchor_id", "source_candidate_id"}

_ORIGINAL_PROVIDER_JSON_SCHEMA = _base._provider_json_schema
_ORIGINAL_PARSE_SEMANTIC = _base._parse_semantic
_ORIGINAL_PROMPT = _base._prompt


def _prop_observation_key(row: dict[str, Any]) -> str:
    return (
        f"{str(row['shot_anchor_id'])}{_PROP_KEY_SEPARATOR}"
        f"{str(row['source_candidate_id'])}"
    )


def _prop_wire_schema(schema: dict[str, Any], payload: _base.ProjectResolutionInput) -> dict[str, Any]:
    """Replace the Provider-owned observation array with exact Source-owned keys."""

    coverage = _base._coverage_contract(_PROP_SKILL_ID, payload)
    keys = [_prop_observation_key(row) for row in coverage]
    if len(keys) != len(set(keys)):
        raise AppError(
            "P9_PROP_COVERAGE_DUPLICATED",
            "CURRENT P8 prop bindings 生成了重复 observation coverage key",
            status_code=409,
        )

    definitions = schema.get("$defs", {})
    observation = definitions.get("PropObservationSemantic")
    if not isinstance(observation, dict):
        raise AppError(
            "P9_PROP_PROVIDER_SCHEMA_INVALID",
            "P9 Prop Provider schema 缺少 PropObservationSemantic",
            status_code=500,
        )
    observation_properties = observation.get("properties")
    if not isinstance(observation_properties, dict):
        raise AppError(
            "P9_PROP_PROVIDER_SCHEMA_INVALID",
            "P9 Prop Provider observation schema 缺少 properties",
            status_code=500,
        )

    decision_properties = {
        name: deepcopy(field_schema)
        for name, field_schema in observation_properties.items()
        if name not in _PROP_SOURCE_FIELDS
    }
    decision_required = [
        name
        for name in observation.get("required", [])
        if name not in _PROP_SOURCE_FIELDS
    ]
    decision_schema: dict[str, Any] = {
        "type": "object",
        "properties": decision_properties,
        "additionalProperties": False,
    }
    if decision_required:
        decision_schema["required"] = decision_required

    root_properties = schema.get("properties", {})
    if "observations" not in root_properties:
        raise AppError(
            "P9_PROP_PROVIDER_SCHEMA_INVALID",
            "P9 Prop Provider schema 缺少 observations",
            status_code=500,
        )
    root_properties["observations"] = {
        "type": "object",
        "properties": {key: deepcopy(decision_schema) for key in keys},
        "required": keys,
        "additionalProperties": False,
        "minProperties": len(keys),
        "maxProperties": len(keys),
    }
    return schema


def _provider_json_schema_v9(
    skill_id: str,
    payload: _base.ProjectResolutionInput | None = None,
) -> dict[str, Any]:
    schema = _ORIGINAL_PROVIDER_JSON_SCHEMA(skill_id, payload)
    if skill_id != _PROP_SKILL_ID or payload is None:
        return schema
    return _prop_wire_schema(schema, payload)


def _parse_prop_wire(text: str) -> PropResolutionSemantic:
    raw = json.loads(_base._json_text(text))
    if not isinstance(raw, dict):
        raise ValueError("Prop wire result must be an object")
    observations = raw.get("observations")
    if not isinstance(observations, dict):
        raise ValueError("Prop observations must be a fixed-key object")

    canonical_observations: list[dict[str, Any]] = []
    for key, decision in observations.items():
        if not isinstance(key, str):
            raise ValueError("Prop observation key must be a string")
        match = re.fullmatch(r"(R\d+)__(R\d+)", key)
        if match is None:
            raise ValueError("Prop observation key is malformed")
        if not isinstance(decision, dict):
            raise ValueError("Prop observation decision must be an object")
        if _PROP_SOURCE_FIELDS.intersection(decision):
            raise ValueError("Prop observation decision must not contain Source pair fields")
        canonical = dict(decision)
        canonical["shot_anchor_id"] = match.group(1)
        canonical["source_candidate_id"] = match.group(2)
        canonical_observations.append(canonical)

    return PropResolutionSemantic.model_validate(
        {
            "groups": raw.get("groups"),
            "observations": canonical_observations,
        }
    )


def _parse_semantic_v9(skill_id: str, text: str) -> BaseModel:
    if skill_id != _PROP_SKILL_ID:
        return _ORIGINAL_PARSE_SEMANTIC(skill_id, text)
    try:
        return _parse_prop_wire(text)
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(
            _base._response_error_code(skill_id, "INVALID"),
            f"{skill_id} Provider 返回结果未通过 P9 v9 Source-owned 数据契约校验"
            f"（{_base._validation_hint(exc)}）",
            status_code=502,
            details={"professional_skill_id": skill_id, "error_type": type(exc).__name__},
        ) from exc


def _prompt_v9(skill_id: str, payload: _base.ProjectResolutionInput) -> str:
    prompt = _ORIGINAL_PROMPT(skill_id, payload)
    if skill_id != _PROP_SKILL_ID:
        return prompt

    prompt = prompt.replace(
        "11. 输出主数组必须与“强制覆盖清单”逐项一一对应；数量必须相同，所有引用令牌必须逐字复制，不得截断、改写、补造或遗漏。可以改变 group_key / resolution_status / reason，但不得改变清单中的 Source 引用字段。",
        "11. prop-resolution 的 observations 使用服务端固定键 object；每个键已经绑定 CURRENT P8 的一个 Shot×Prop candidate observation。只填写每个固定键下的 group_key / resolution_status / reason，禁止改键、漏键、新增键，也禁止在 value 内回写 Source pair 字段。",
    )
    prompt = prompt.replace(
        "强制覆盖清单（输出主数组必须完整覆盖，引用令牌逐字复制）：",
        "强制覆盖清单（Prop Source pair 由下方 fixed observation keys 与 strict schema 所有）：",
    )
    fixed_keys = [
        _prop_observation_key(row)
        for row in _base._coverage_contract(_PROP_SKILL_ID, payload)
    ]
    return (
        prompt
        + "\n\nP9 v9 Prop observation wire contract: "
        + P9_PROP_WIRE_CONTRACT
        + "\n固定 observation keys（必须全部保留，禁止新增；value 只做归一判断）：\n"
        + json.dumps(fixed_keys, ensure_ascii=False, separators=(",", ":"))
    )


# Patch the v8 implementation at package-load time. Provider classes resolve these module globals
# at call time, so Cloud Ark and local vLLM paths share one v9 contract without duplicating the
# upload/transport lifecycle. The published P9 schemas and composition service remain untouched.
_base.P9_PROMPT_VERSION = P9_PROMPT_VERSION
_base._provider_json_schema = _provider_json_schema_v9
_base._parse_semantic = _parse_semantic_v9
_base._prompt = _prompt_v9
