import json
import re
from dataclasses import dataclass
from typing import Protocol

from arkruntime import Ark

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.replica_pipeline.schemas import CharacterVisualDesignAuthoringResult, CharacterVisualDesignPacket
from app.skills.professional import ProfessionalSkillDetail, get_professional_skill_detail


SKILL_ID = "character-visual-design"
MAX_CHARACTER_VISUAL_BATCH_SIZE = 12
MAX_OUTPUT_TOKENS = 32768


@dataclass(frozen=True)
class CharacterVisualDesignInput:
    skill: ProfessionalSkillDetail
    characters: tuple[dict, ...]


@dataclass(frozen=True)
class CharacterVisualDesignResult:
    content: CharacterVisualDesignAuthoringResult
    remote_job_id: str | None = None


class CharacterVisualDesignProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def design(self, payload: CharacterVisualDesignInput) -> CharacterVisualDesignResult: ...


def _json_object(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("CHARACTER_VISUAL_DESIGN_PROVIDER_INVALID", "角色视觉设计 Provider 未返回 JSON object", status_code=502)


def _authoring_prompt(payload: CharacterVisualDesignInput) -> str:
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(payload.skill.provider_rules, 1))
    schema = CharacterVisualDesignAuthoringResult.model_json_schema()
    return f"""你正在执行 AI Drama Studio 的 Character Visual Design Professional Skill。

Skill：{payload.skill.id}@{payload.skill.version}

这是图片模型 Prompt Skill 之前的角色视觉设计层。你只负责把正式角色语义身份转换成稳定、可执行、可复用的 CharacterVisualDesignPacket，不生成图片，也不编译 Z-Image/Qwen 专属语法。

硬规则：
- 必须逐项精确覆盖输入 character_id，不得漏项、重复、增加、合并或拆分角色。
- 输入中的 localized_storyboard_identity / appearance 与 optional_target_bible 都属于身份事实；TARGET_BIBLE 存在时优先作为稳定身份约束，本土化分镜只补充可观察外观证据。
- 可以把已有外观事实整理成生产可执行的脸型、发型、体态、服装材质/颜色和识别锚点，但不得发明新的角色身份、族裔、职业、亲属关系、伤疤、纹身、饰品或标志性道具。
- storyboard_evidence 只用于判断哪些信息是稳定外观；不得把剧情动作、手机等临时道具、场景背景、镜头、对白、临时情绪写进固定角色设计。
- face_design / hair_design / body_design / wardrobe_design 必须具体且彼此不冲突；证据不足的细节用中性、保守的视觉实现，不得伪造人物经历。
- continuity_rules 必须锁定脸部身份、发型、体态、服装拓扑、鞋履和稳定识别点，供后续多次生成保持一致。
- positive_guidance 只写正向稳定视觉方向；negative_constraints 写必须避免的身份漂移，不写多视图排版要求。
- 只输出符合 JSON Schema 的 JSON object，不输出 Markdown 或额外解释。

Professional Skill rules：
{rules}

Professional Skill manual：
{payload.skill.manual}

待设计角色：
{json.dumps(payload.characters, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


class DoubaoCharacterVisualDesignProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("CHARACTER_VISUAL_DESIGN_PROVIDER_NOT_CONFIGURED", "角色视觉设计 Skill 的火山引擎执行 Provider 尚未配置", status_code=409)

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "CLOUD_TEXT_SKILL_EXECUTOR",
            "prompt_contract": "character-visual-design-v1",
            "response_contract": "STRICT_JSON_SCHEMA",
        }

    def design(self, payload: CharacterVisualDesignInput) -> CharacterVisualDesignResult:
        assert self.settings.p7_doubao_api_key is not None
        client = Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _authoring_prompt(payload)}]}],
            thinking={"type": "enabled"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "character_visual_design_batch",
                    "schema": CharacterVisualDesignAuthoringResult.model_json_schema(),
                    "strict": True,
                }
            },
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        text = getattr(response, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            chunks: list[str] = []
            for item in getattr(response, "output", None) or []:
                for part in getattr(item, "content", None) or []:
                    if getattr(part, "type", None) == "output_text" and getattr(part, "text", None):
                        chunks.append(str(part.text))
            text = "".join(chunks)
        if not isinstance(text, str) or not text.strip():
            raise AppError("CHARACTER_VISUAL_DESIGN_PROVIDER_EMPTY", "角色视觉设计 Provider 未返回可用文本", status_code=502)
        try:
            content = CharacterVisualDesignAuthoringResult.model_validate_json(_json_object(text))
        except AppError:
            raise
        except Exception as exc:
            raise AppError("CHARACTER_VISUAL_DESIGN_PROVIDER_SCHEMA_INVALID", "角色视觉设计 Provider 输出不符合 typed contract", status_code=502) from exc
        return CharacterVisualDesignResult(
            content=content,
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


def character_visual_design_provider(settings: Settings | None = None) -> CharacterVisualDesignProvider:
    return DoubaoCharacterVisualDesignProvider(settings or get_settings())


def character_visual_design_skill() -> ProfessionalSkillDetail:
    return get_professional_skill_detail(SKILL_ID)


def validate_character_visual_design_batch(
    expected_characters: list[dict],
    authored: CharacterVisualDesignAuthoringResult,
) -> dict[str, CharacterVisualDesignPacket]:
    expected_ids = [str(item["character_id"]) for item in expected_characters]
    actual_ids = [item.character_id for item in authored.characters]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise AppError(
            "CHARACTER_VISUAL_DESIGN_COVERAGE_INVALID",
            "角色视觉设计 Provider 必须精确覆盖本批全部角色",
            status_code=502,
            details={"expected": expected_ids, "actual": actual_ids},
        )
    return {item.character_id: item for item in authored.characters}


def build_character_visual_identity(character: dict) -> CharacterVisualDesignPacket:
    """Compatibility helper for callers that already hold a fully authored packet-shaped dict."""
    return CharacterVisualDesignPacket.model_validate(character)

