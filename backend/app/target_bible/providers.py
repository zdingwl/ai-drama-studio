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
from app.target_bible.schemas import (
    P11_PROMPT_VERSION,
    P11_PRESERVATION_CONTRACT,
    P11_SCHEMA_VERSION,
    P11_SKILL_ID,
    P11_TARGET_CONTRACT,
    PreservationLock,
    ReplicaTargetBibleSemantic,
)


P11_MAX_OUTPUT_TOKENS = 32768


@dataclass(frozen=True)
class ReplicaTargetBibleProviderInput:
    source_snapshot: dict
    target_language: str
    target_region: str
    scene_strategy: str
    visual_style: str | None
    preservation_locks: tuple[PreservationLock, ...]


@dataclass(frozen=True)
class ReplicaTargetBibleProviderResult:
    semantic: ReplicaTargetBibleSemantic
    remote_job_id: str | None = None


class ReplicaTargetBibleProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def design(self, payload: ReplicaTargetBibleProviderInput) -> ReplicaTargetBibleProviderResult: ...


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
    raise AppError("P11_PROVIDER_RESPONSE_INVALID", "P11 Provider 未返回 JSON object", status_code=502)


def _parse(text: str) -> ReplicaTargetBibleSemantic:
    try:
        return ReplicaTargetBibleSemantic.model_validate_json(_json_text(text))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "P11_PROVIDER_RESPONSE_INVALID",
            f"P11 Provider 返回结果未通过数据契约校验（{type(exc).__name__}）",
            status_code=502,
        ) from exc


def _source_identity_manifest(payload: ReplicaTargetBibleProviderInput) -> dict[str, list[dict[str, str]]]:
    snapshot = payload.source_snapshot
    return {
        "characters": [
            {
                "source_character_id": str(item.get("character_id") or item.get("entity_id") or ""),
                "display_name": str(item.get("display_name") or ""),
            }
            for item in snapshot.get("source_characters", {}).get("entities", [])
        ],
        "scenes": [
            {
                "source_scene_id": str(item.get("scene_id") or item.get("entity_id") or ""),
                "display_name": str(item.get("display_name") or ""),
            }
            for item in snapshot.get("source_scenes", {}).get("entities", [])
        ],
        "props": [
            {
                "source_prop_id": str(item.get("prop_id") or item.get("entity_id") or ""),
                "display_name": str(item.get("display_name") or ""),
            }
            for item in snapshot.get("source_props", {}).get("entities", [])
        ],
    }


def _prompt(payload: ReplicaTargetBibleProviderInput) -> str:
    skill = get_professional_skill(P11_SKILL_ID)
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    manifest = _source_identity_manifest(payload)
    schema = ReplicaTargetBibleSemantic.model_json_schema()
    locks = [item.model_dump(mode="json") for item in payload.preservation_locks]
    return f"""你正在执行 AI Drama Studio P11 Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

这是 Replica Target Bible 阶段。CURRENT SOURCE_VIDEO_SNAPSHOT 是唯一 Source 世界版本锚点。

目标配置：
- target_language: {payload.target_language}
- target_region: {payload.target_region}
- scene_strategy: {payload.scene_strategy}
- visual_style: {payload.visual_style or '未指定，由你给出与目标版本一致的视觉方向'}

最高规则：
1. 故事不乱改，节奏不重做，文化和表达才本土化。
2. 下方 preservation_locks 由服务端确定性生成，你只能遵守，不能删除、合并、重排或重写锁定事实。
3. Source Snapshot 只读；禁止修正 Source 人物、场景、道具、对白、Shot 或故事事实。
4. characters / scenes / props 必须与 source_identity_manifest 一一完整覆盖；source_*_id 必须逐字复制，不能遗漏、重复、截断或创造新 Source id。
5. 你只输出 Target 设计语义；不得输出数据库 ID、Artifact ID、revision、fingerprint。
6. 不生成完整 Target Script、逐句 Target Dialogue、Target Storyboard、TTS、Timing 或 Generation 参数。
7. Target 人物身份/姓名/外形、场景文化环境、道具替代、世界语境、称谓/表达策略、视觉与连续性可以本土化，但不得改变人物故事功能、Scene order、Story Beat timing 或 Shot rhythm baseline。
8. 只输出符合 JSON Schema 的单个 object，不输出 Markdown、解释或思考过程。

Professional Skill rules:
{rules}

Preservation locks:
{json.dumps(locks, ensure_ascii=False, separators=(",", ":"))}

Source identity manifest（必须完整一对一覆盖）：
{json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))}

CURRENT SOURCE_VIDEO_SNAPSHOT typed content：
{json.dumps(payload.source_snapshot, ensure_ascii=False, separators=(",", ":"))}

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
        raise AppError("P11_PROVIDER_RESPONSE_EMPTY", "P11 Provider 未返回可用文本", status_code=502)
    return "".join(chunks)


def _profile(selection: SourceUnderstandingProvider, provider: str, model: str, mode: str) -> dict:
    skill = get_professional_skill(P11_SKILL_ID)
    return {
        "selection": selection.value,
        "provider": provider,
        "model": model,
        "mode": mode,
        "prompt_version": P11_PROMPT_VERSION,
        "schema_version": P11_SCHEMA_VERSION,
        "target_contract": P11_TARGET_CONTRACT,
        "preservation_contract": P11_PRESERVATION_CONTRACT,
        "professional_skill_id": skill.id,
        "professional_skill_version": skill.version,
    }


class DoubaoReplicaTargetBibleProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("P11_PROVIDER_NOT_CONFIGURED", "火山引擎 P11 Provider 尚未配置", status_code=409)

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

    def design(self, payload: ReplicaTargetBibleProviderInput) -> ReplicaTargetBibleProviderResult:
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
            max_output_tokens=P11_MAX_OUTPUT_TOKENS,
        )
        status = str(getattr(response, "status", "") or "").lower()
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None) if details is not None else None
            raise AppError(
                "P11_PROVIDER_RESPONSE_INCOMPLETE",
                f"P11 Provider 输出未完成（{str(reason or 'unknown')}）",
                status_code=502,
            )
        semantic = _parse(_ark_response_text(response))
        return ReplicaTargetBibleProviderResult(
            semantic=semantic,
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


class LocalQwenReplicaTargetBibleProvider:
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

    def design(self, payload: ReplicaTargetBibleProviderInput) -> ReplicaTargetBibleProviderResult:
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
                    "max_tokens": P11_MAX_OUTPUT_TOKENS,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise AppError("P11_PROVIDER_RESPONSE_EMPTY", "P11 Provider 未返回 choices", status_code=502)
        text = (choices[0].get("message") or {}).get("content")
        if not isinstance(text, str) or not text.strip():
            raise AppError("P11_PROVIDER_RESPONSE_EMPTY", "P11 Provider 未返回可用文本", status_code=502)
        return ReplicaTargetBibleProviderResult(
            semantic=_parse(text),
            remote_job_id=str(body.get("id") or "") or None,
        )


def build_replica_target_bible_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> ReplicaTargetBibleProvider:
    # P11 v1 intentionally reuses the project's existing reasoning-runtime selection.
    # The Professional Skill remains model-independent; a dedicated target-provider
    # preference can be added later without changing the P11 Artifact contract.
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoReplicaTargetBibleProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenReplicaTargetBibleProvider(
            settings,
            selection=selection,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        effective = SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL
        return LocalQwenReplicaTargetBibleProvider(
            settings,
            selection=effective,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P11_PROVIDER_UNSUPPORTED",
        "当前 P11 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
