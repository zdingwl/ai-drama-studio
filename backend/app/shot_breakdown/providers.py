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
from app.shot_breakdown.schemas import EpisodeShotBreakdownSemantic
from app.skills.professional import get_professional_skill


P8_PROFESSIONAL_SKILL_ID = "shot-breakdown"
P8_PROMPT_VERSION = "p8-shot-breakdown-v1"
P8_SCHEMA_VERSION = "1.0"
P8_SOURCE_TRUTH_CONTRACT = "source-bible-shot-facts-v1"


@dataclass(frozen=True)
class EpisodeShotBreakdownInput:
    source_path: Path
    source_filename: str
    mime_type: str
    episode_id: str
    episode_order: int
    duration_us: int
    source_language: str | None
    source_bible_episode: dict
    shot_context: list[dict]


@dataclass(frozen=True)
class EpisodeShotBreakdownProviderResult:
    semantic: EpisodeShotBreakdownSemantic
    remote_job_id: str | None


class ShotBreakdownProvider(Protocol):
    provider_name: str
    model_name: str

    @property
    def profile(self) -> dict: ...

    def analyze(self, payload: EpisodeShotBreakdownInput) -> EpisodeShotBreakdownProviderResult: ...


def _professional_skill():
    return get_professional_skill(P8_PROFESSIONAL_SKILL_ID)


def _clean_json_schema(value: Any) -> Any:
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
    return _clean_json_schema(EpisodeShotBreakdownSemantic.model_json_schema())


def _json_text(text: str) -> str:
    value = text.strip()
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
    raise ValueError("P8 provider response did not contain a JSON object")


def _parse_semantic(text: str) -> EpisodeShotBreakdownSemantic:
    return EpisodeShotBreakdownSemantic.model_validate_json(_json_text(text))


def _prompt(payload: EpisodeShotBreakdownInput) -> str:
    skill = _professional_skill()
    skill_rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    bible_json = json.dumps(payload.source_bible_episode, ensure_ascii=False, separators=(",", ":"))
    shots_json = json.dumps(payload.shot_context, ensure_ascii=False, separators=(",", ":"))
    schema_json = json.dumps(_response_schema(), ensure_ascii=False, separators=(",", ":"))
    return f"""你正在执行 AI Drama Studio Professional Skill：{skill.name}（{skill.id}@{skill.version}）。
任务是 P8《带 Source Bible 的逐镜精细拉片》，不是 P7 整集故事重写，也不是 P9 身份归一。

Professional Skill 执行规则：
{skill_rules}

Source Truth 权威层级：
1. 当前上传的完整 Episode 是视觉、表演与声音现场的最高层原片事实源；你必须直接观看完整 Episode。
2. CURRENT P5 Shot Anchors 已由服务端给出；你只能按 shot_number 分析，不能输出或修改 start/end/duration。
3. CURRENT P6 canonical dialogue/OCR 已由服务端给出；你只能为已提供的 utterance_number 标 delivery，不能输出 dialogue text，也不能重新听写。
4. CURRENT P7 SOURCE_BIBLE 是整集人物、关系、故事、场景、道具、Story/Rhythm 全局知识；不得让每个 Shot 各猜一套整集故事。
5. character_ids / scene_ids / prop_ids 只能从下面 SOURCE_BIBLE 已存在的 candidate ID 中选择；不创建新 ID，不做 Speaker→Character 最终归一。
6. sound_effects / ambience 只写该 Shot 实际可听见的声音；无法可靠判断就留空。
7. 镜头语言无法可靠判断时，用“无法可靠判断”等明确文本，不为了填满字段而猜测。
8. 必须对 shot_context 中每个 shot_number 恰好输出一次，不能漏镜、增镜、重复或重编号。
9. 每个 Shot 的 dialogue_annotations 必须与该 Shot 的 canonical_dialogue_overlaps 中 utterance_number 集合完全一致；不确定 delivery 时填 UNKNOWN。
10. 输出模型禁止额外字段；不得加入 shot 时间、dialogue text、speaker identity、推理过程或解释。

Episode:
- episode_id: {payload.episode_id}
- episode_order: {payload.episode_order}
- source_filename: {payload.source_filename}
- duration_us: {payload.duration_us}
- source_language: {payload.source_language or 'unknown'}

CURRENT SOURCE_BIBLE（本 Episode 全局上下文）:
{bible_json}

CURRENT Shot Context（P5 权威边界 + 服务端计算的 P6 overlap；这些时间只用于观察定位，不得在输出中重写）:
{shots_json}

只输出一个符合下列 Schema 的 JSON object，不输出 Markdown、解释、思考过程或额外文本。
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


class DoubaoSeedShotBreakdownProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError(
                "P8_PROVIDER_NOT_CONFIGURED",
                "火山引擎 P8 Provider 尚未配置 AI_DRAMA_P7_DOUBAO_API_KEY",
                status_code=409,
            )

    @property
    def video_fps(self) -> float:
        return min(10.0, max(4.0, float(self.settings.p7_doubao_video_fps)))

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
            "video_fps": self.video_fps,
            "structured_output": "STRICT_JSON_SCHEMA_PROMPT_PLUS_SERVER_BINDING",
            "prompt_version": P8_PROMPT_VERSION,
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P8_SOURCE_TRUTH_CONTRACT,
        }

    @property
    def _api_key(self) -> str:
        assert self.settings.p7_doubao_api_key is not None
        return self.settings.p7_doubao_api_key.get_secret_value()

    def analyze(self, payload: EpisodeShotBreakdownInput) -> EpisodeShotBreakdownProviderResult:
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
                                "fps": self.video_fps,
                            },
                            {"type": "input_text", "text": _prompt(payload)},
                        ],
                    }
                ],
                thinking={"type": "enabled"},
            )
            semantic = _parse_semantic(_ark_response_text(response))
            response_id = str(getattr(response, "id", "") or "") or None
            return EpisodeShotBreakdownProviderResult(semantic=semantic, remote_job_id=response_id)
        finally:
            if uploaded_file_id:
                try:
                    client.files.delete(uploaded_file_id)
                except Exception:
                    pass


class LocalQwenShotBreakdownProvider:
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
            "structured_output": "STRICT_JSON_SCHEMA_PROMPT_PLUS_SERVER_BINDING",
            "prompt_version": P8_PROMPT_VERSION,
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P8_SOURCE_TRUTH_CONTRACT,
        }

    def analyze(self, payload: EpisodeShotBreakdownInput) -> EpisodeShotBreakdownProviderResult:
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
                    "temperature": 0.1,
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
        return EpisodeShotBreakdownProviderResult(semantic=semantic, remote_job_id=response_id)


def build_shot_breakdown_provider(
    settings: Settings,
    selection: SourceUnderstandingProvider,
) -> ShotBreakdownProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return DoubaoSeedShotBreakdownProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return LocalQwenShotBreakdownProvider(
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
        return LocalQwenShotBreakdownProvider(
            settings,
            selection=effective_selection,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError(
        "P8_PROVIDER_UNSUPPORTED",
        "当前 P8 Provider 未实现",
        status_code=422,
        details={"provider": str(selection)},
    )
