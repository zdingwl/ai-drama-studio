import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from arkruntime import Ark
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.projects.enums import SourceUnderstandingProvider
from app.skills.professional import get_professional_skill
from app.understanding.schemas import (
    ClaimGrounding,
    ClaimSupportLevel,
    EpisodeUnderstandingSemantic,
)


P7_PROFESSIONAL_SKILL_ID = "source-video-understanding"
P7_GROUNDING_CONTRACT = "grounded-source-truth-v1"


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


def _professional_skill():
    return get_professional_skill(P7_PROFESSIONAL_SKILL_ID)


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
    # Thinking models may expose raw <think> blocks when the local vLLM server is not launched with
    # a reasoning parser. P7 only persists the final structured answer, never hidden reasoning.
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.IGNORECASE | re.DOTALL).strip()
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


def _validate_grounding(
    label: str,
    grounding: ClaimGrounding,
    *,
    payload: EpisodeUnderstandingInput,
    dialogue_ids: set[str],
    visual_ids: set[str],
) -> None:
    invalid_dialogue = sorted(set(grounding.dialogue_evidence_ids) - dialogue_ids)
    invalid_visual = sorted(set(grounding.visual_text_evidence_ids) - visual_ids)
    if invalid_dialogue or invalid_visual:
        raise ValueError(
            f"{label} grounding referenced non-current Source Evidence: "
            f"dialogue={invalid_dialogue}, visual_text={invalid_visual}"
        )
    for time_range in grounding.video_time_ranges:
        if time_range.end_us > payload.duration_us:
            raise ValueError(
                f"{label} grounding video time range exceeded Episode duration: "
                f"end_us={time_range.end_us}, duration_us={payload.duration_us}"
            )


def validate_episode_understanding_grounding(
    semantic: EpisodeUnderstandingSemantic,
    payload: EpisodeUnderstandingInput,
) -> None:
    """Validate claim-level grounding before semantic output can enter SOURCE_BIBLE.

    This is intentionally provider-side because the provider has the exact Episode evidence payload
    used for this call. The later service validation remains the final Artifact guardrail.
    """
    dialogue_ids = {str(item.get("id")) for item in payload.evidence_payload.get("dialogue", []) if item.get("id")}
    visual_ids = {str(item.get("id")) for item in payload.evidence_payload.get("visual_text", []) if item.get("id")}

    analysis = semantic.overall_analysis
    if len(analysis.world_rule_groundings) != len(analysis.world_rules):
        raise ValueError("world_rules must have one world_rule_groundings item per rule")
    _validate_grounding(
        "overall_analysis.story_background",
        analysis.story_background_grounding,
        payload=payload,
        dialogue_ids=dialogue_ids,
        visual_ids=visual_ids,
    )
    for index, grounding in enumerate(analysis.world_rule_groundings):
        if grounding.support_level != ClaimSupportLevel.FACT:
            raise ValueError(f"world_rules[{index}] must be FACT, otherwise omit it from world_rules")
        _validate_grounding(
            f"overall_analysis.world_rules[{index}]",
            grounding,
            payload=payload,
            dialogue_ids=dialogue_ids,
            visual_ids=visual_ids,
        )

    for character in semantic.characters:
        _validate_grounding(
            f"character[{character.character_id}].identity",
            character.identity_grounding,
            payload=payload,
            dialogue_ids=dialogue_ids,
            visual_ids=visual_ids,
        )
    for relation in semantic.relationships:
        _validate_grounding(
            f"relationship[{relation.source_character_id}->{relation.target_character_id}]",
            relation.grounding,
            payload=payload,
            dialogue_ids=dialogue_ids,
            visual_ids=visual_ids,
        )
    for scene in semantic.scenes:
        _validate_grounding(
            f"scene[{scene.scene_id}]",
            scene.grounding,
            payload=payload,
            dialogue_ids=dialogue_ids,
            visual_ids=visual_ids,
        )
    for prop in semantic.key_props:
        _validate_grounding(
            f"prop[{prop.prop_id}].story_function",
            prop.story_function_grounding,
            payload=payload,
            dialogue_ids=dialogue_ids,
            visual_ids=visual_ids,
        )
    for event in semantic.story_events:
        _validate_grounding(
            f"story_event[{event.event_id}]",
            event.grounding,
            payload=payload,
            dialogue_ids=dialogue_ids,
            visual_ids=visual_ids,
        )


def _parse_semantic(text: str, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingSemantic:
    semantic = EpisodeUnderstandingSemantic.model_validate_json(_json_text(text))
    validate_episode_understanding_grounding(semantic, payload)
    return semantic


def _prompt(payload: EpisodeUnderstandingInput) -> str:
    skill = _professional_skill()
    evidence_json = json.dumps(payload.evidence_payload, ensure_ascii=False, separators=(",", ":"))
    shot_json = json.dumps(payload.shot_hints, ensure_ascii=False, separators=(",", ":"))
    schema_json = json.dumps(_response_schema(), ensure_ascii=False, separators=(",", ":"))
    skill_rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    return f"""你正在执行 AI Drama Studio Professional Skill：{skill.name}（{skill.id}@{skill.version}）。
任务产物是 P7《源作概览分析》，不是 P8 分镜表。

Professional Skill 执行规则：
{skill_rules}

Grounding 输出约定：
1. support_level 只能是 FACT / INFERENCE / UNKNOWN。
2. FACT 必须至少包含一个 CURRENT dialogue_evidence_id、CURRENT visual_text_evidence_id，或完整 Episode 中明确的 video_time_ranges。
3. INFERENCE 可以引用支持它的 Evidence / 视频时间，但必须保持“推断”身份，不能在其他字段中偷换成客观事实。
4. UNKNOWN 表示原片无法可靠确认；不要为了让内容完整而补写。
5. story_background_grounding 必须说明 story_background 中历史/关系性事实的可信等级。
6. world_rules 不是社会常识列表。每条 world_rule 必须是本作品内部已确认 FACT，并在 world_rule_groundings 中按相同索引提供依据；如果没有，两个数组都输出空数组。
7. character.identity_grounding 用于姓名/身份等事实；人物性格与剧情功能属于分析，不要伪装成身份事实。
8. relationship.grounding 用于夫妻/亲属/邻居/同事/婚姻年限等关系事实。
9. prop.story_function_grounding 如果没有明确依据，使用 UNKNOWN，并把 story_function 写成“未确认明确剧情功能”。
10. scene / story_event grounding 可使用完整 Episode 视频时间窗口作为直接视觉依据。

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

所有时间使用微秒，范围必须位于 0 到 {payload.duration_us} 之间。
只输出一个 JSON object，不要输出 Markdown、解释、思考过程或额外文本。
内容使用与原片相适应的自然中文表达。

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
        skill = _professional_skill()
        return {
            "selection": SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API.value,
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "CLOUD_API",
            "base_url": self.settings.p7_doubao_base_url,
            "video_input": "ARK_FILES_API_FULL_EPISODE",
            "video_fps": self.settings.p7_doubao_video_fps,
            "structured_output": "JSON_SCHEMA_PROMPT_PLUS_GROUNDING_PLUS_SERVER_VALIDATION",
            "prompt_version": "p7-source-bible-v1",
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "grounding_contract": P7_GROUNDING_CONTRACT,
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
            semantic = _parse_semantic(_ark_response_text(response), payload)
            response_id = str(getattr(response, "id", "") or "") or None
            return EpisodeUnderstandingProviderResult(semantic=semantic, remote_job_id=response_id)
        finally:
            if uploaded_file_id:
                try:
                    client.files.delete(uploaded_file_id)
                except Exception:
                    pass


class LocalQwenSourceEpisodeUnderstandingProvider:
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

    @property
    def profile(self) -> dict:
        skill = _professional_skill()
        return {
            "selection": self.selection.value,
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "LOCAL_OPENAI_COMPATIBLE",
            "base_url": self.base_url,
            "video_input": "VLLM_FILE_URL_FULL_EPISODE",
            "structured_output": "JSON_SCHEMA_PROMPT_PLUS_GROUNDING_PLUS_SERVER_VALIDATION",
            "prompt_version": "p7-source-bible-v1",
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "grounding_contract": P7_GROUNDING_CONTRACT,
        }

    def analyze(self, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingProviderResult:
        source_uri = payload.source_path.resolve().as_uri()
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None:
            key = self.api_key.get_secret_value().strip()
            if key:
                headers["Authorization"] = f"Bearer {key}"
        timeout = httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
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
        semantic = _parse_semantic(text, payload)
        response_id = str(body.get("id") or "") or None
        return EpisodeUnderstandingProviderResult(semantic=semantic, remote_job_id=response_id)


def build_source_episode_understanding_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> SourceEpisodeUnderstandingProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoSeedSourceEpisodeUnderstandingProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenSourceEpisodeUnderstandingProvider(
            settings,
            selection=selection,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {
        SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL,
        SourceUnderstandingProvider.QWEN3_VL_LOCAL,
    }:
        effective_selection = SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL
        return LocalQwenSourceEpisodeUnderstandingProvider(
            settings,
            selection=effective_selection,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P7_PROVIDER_UNSUPPORTED",
        "当前 P7 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
