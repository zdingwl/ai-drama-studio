import json
import re
from dataclasses import dataclass
from typing import Protocol

from arkruntime import Ark

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.replica_pipeline.image_model_skills import ImageModelPromptSkillBinding
from app.replica_pipeline.schemas import AssetImagePromptAuthoringResult, AssetImagePromptAuthoredEntity
from app.skills.professional import ProfessionalSkillDetail
from app.target_assets.schemas import TargetAssetType


MAX_ASSET_PROMPT_BATCH_SIZE = 12
MAX_OUTPUT_TOKENS = 32768
CHARACTER_LAYOUT_ANCHORS = (
    "front full-body view",
    "side full-body view",
    "back full-body view",
    "face close-up",
    "same character",
)


def _assert_execution_english(label: str, value: str, *, target_entity_id: str) -> None:
    latin = len(re.findall(r"[A-Za-z]", value))
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))
    if latin < 20 or (cjk > 8 and latin < cjk * 2):
        raise AppError(
            "ASSET_IMAGE_PROMPT_EXECUTION_LANGUAGE_INVALID",
            f"{label} 必须是可直接交给 Z-Image Turbo 的英文视觉提示内容",
            status_code=502,
            details={"target_entity_id": target_entity_id},
        )


def _json_object(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("ASSET_IMAGE_PROMPT_PROVIDER_INVALID", "资产 Prompt Skill Provider 未返回 JSON object", status_code=502)


@dataclass(frozen=True)
class AssetPromptAuthorInput:
    binding: ImageModelPromptSkillBinding
    skill: ProfessionalSkillDetail
    assets: tuple[dict, ...]


@dataclass(frozen=True)
class AssetPromptAuthorResult:
    content: AssetImagePromptAuthoringResult
    remote_job_id: str | None = None


class AssetPromptAuthorProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...
    def author(self, payload: AssetPromptAuthorInput) -> AssetPromptAuthorResult: ...


def _authoring_prompt(payload: AssetPromptAuthorInput) -> str:
    schema = AssetImagePromptAuthoringResult.model_json_schema()
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(payload.skill.provider_rules, 1))
    return f"""你正在执行 AI Drama Studio 的图片模型专属 Professional Skill。

目标图片模型：{payload.binding.model_id}
Prompt Skill：{payload.skill.id}@{payload.skill.version}
Prompt Contract：{payload.binding.prompt_contract}

你收到的不是要原样塞进图片模型的人物小传，而是正式本土化分镜中已经提取好的资产和它实际出现的镜头视觉证据。你的职责是分析这些证据，只保留可观察的稳定视觉信息，然后编译成图片模型可以直接执行的最终提示词。

硬规则：
- 必须逐项精确覆盖输入 target_entity_id，不得漏项、重复、增加、合并或拆分资产。
- image_prompt 以具体清晰的英文为主，直接服务 {payload.binding.model_id}；review_prompt_zh 使用简体中文解释出图目标。
- 人物关系、婚姻、亲属、同事等叙事关系不能导致单人物资产图出现第二个人。
- CHARACTER 必须是一张横向 production reference sheet，严格包含 front full-body view、side full-body view、back full-body view、face close-up，并明确 same character；三个全身视图使用中性站姿，面部特写是正面头肩像。
- CHARACTER 禁止四个全身方向、单张情绪肖像、情侣照、剧情动作场景、生活照；除非稳定身份绝对需要，否则不要让人物拿手机或其他剧情道具。
- SCENE 只表现稳定环境身份、空间布局、材质、landmarks、光照和色彩，不把剧情中的人物带进环境资产图。
- PROP 只表现稳定物体身份、形态、尺度、材质、颜色和标志性细节，不加入无关人物/场景。
- 当前 Turbo Runtime 使用 zeroed negative conditioning，因此关键排除项必须同时作为 `Do not ...` 约束写进 image_prompt；negative_prompt 也必须返回用于审计。
- 不修改 target entity identity，不创造 Artifact/media/id，不生成视频提示词。
- 只输出符合 JSON Schema 的 JSON object，不输出 Markdown 或额外解释。

Professional Skill rules：
{rules}

Professional Skill manual：
{payload.skill.manual}

待编译资产及本土化分镜证据：
{json.dumps(payload.assets, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


class DoubaoAssetPromptAuthor:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("ASSET_IMAGE_PROMPT_PROVIDER_NOT_CONFIGURED", "资产图 Prompt Skill 的火山引擎执行 Provider 尚未配置", status_code=409)

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "CLOUD_TEXT_SKILL_EXECUTOR",
            "prompt_contract": "z-image-turbo-replica-assets-v1",
            "response_contract": "STRICT_JSON_SCHEMA",
        }

    def author(self, payload: AssetPromptAuthorInput) -> AssetPromptAuthorResult:
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
                    "name": "z_image_turbo_asset_prompt_batch",
                    "schema": AssetImagePromptAuthoringResult.model_json_schema(),
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
            raise AppError("ASSET_IMAGE_PROMPT_PROVIDER_EMPTY", "资产图 Prompt Skill Provider 未返回可用文本", status_code=502)
        try:
            content = AssetImagePromptAuthoringResult.model_validate_json(_json_object(text))
        except AppError:
            raise
        except Exception as exc:
            raise AppError("ASSET_IMAGE_PROMPT_PROVIDER_SCHEMA_INVALID", "资产图 Prompt Skill Provider 输出不符合 typed contract", status_code=502) from exc
        return AssetPromptAuthorResult(
            content=content,
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


def asset_prompt_author_provider(settings: Settings | None = None) -> AssetPromptAuthorProvider:
    # Step 3 prompt authoring is its own Professional Skill execution policy. It does not
    # inherit the Step 1 source-understanding provider, matching Step 2's explicit Ark policy.
    return DoubaoAssetPromptAuthor(settings or get_settings())


def validate_authored_asset_batch(
    expected_assets: list[dict],
    authored: AssetImagePromptAuthoringResult,
) -> dict[str, AssetImagePromptAuthoredEntity]:
    expected_ids = [str(item["target_entity_id"]) for item in expected_assets]
    actual_ids = [item.target_entity_id for item in authored.assets]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise AppError(
            "ASSET_IMAGE_PROMPT_PROVIDER_COVERAGE_INVALID",
            "资产图 Prompt Skill Provider 必须精确覆盖本批全部资产",
            status_code=502,
            details={"expected": expected_ids, "actual": actual_ids},
        )
    by_id = {item.target_entity_id: item for item in authored.assets}
    asset_type_by_id = {str(item["target_entity_id"]): str(item["asset_type"]) for item in expected_assets}
    for entity_id, item in by_id.items():
        if asset_type_by_id[entity_id] == TargetAssetType.CHARACTER.value:
            prompt = item.image_prompt.lower()
            missing = [anchor for anchor in CHARACTER_LAYOUT_ANCHORS if anchor not in prompt]
            if missing:
                raise AppError(
                    "ASSET_IMAGE_CHARACTER_LAYOUT_INVALID",
                    "人物资产提示词必须是正面全身、侧面全身、背面全身加面部特写，并明确同一人物",
                    status_code=502,
                    details={"target_entity_id": entity_id, "missing_anchors": missing},
                )
        _assert_execution_english("image_prompt", item.image_prompt, target_entity_id=entity_id)
        if item.negative_prompt.strip():
            _assert_execution_english("negative_prompt", item.negative_prompt, target_entity_id=entity_id)
        if len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", item.review_prompt_zh)) < 4:
            raise AppError(
                "ASSET_IMAGE_PROMPT_REVIEW_LANGUAGE_INVALID",
                "资产图 Prompt Skill 必须提供简体中文审核说明",
                status_code=502,
                details={"target_entity_id": entity_id},
            )
    return by_id
