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
CHARACTER_RUNTIME_LAYOUT_TOKENS = (
    "front full-body view",
    "side full-body view",
    "back full-body view",
    "face close-up",
    "reference sheet",
    "contact sheet",
    "multi-panel",
    "turnaround",
    "collage",
    "split screen",
)

_CHARACTER_LAYOUT_NEGATION_RE = re.compile(
    r"\b(?:do\s+not|don['’]?t|no|never|avoid|without|must\s+not|should\s+not|exclude(?:d|s|ing)?|forbid(?:s|den|ding)?)\b",
    flags=re.IGNORECASE,
)
_CHARACTER_LAYOUT_CONTRAST_RE = re.compile(r"\b(?:but|however|instead|rather)\b", flags=re.IGNORECASE)


def _positive_character_layout_tokens(prompt: str) -> list[str]:
    """Return Runtime-owned layout tokens that are requested positively.

    Older Prompt Skill revisions could repeat Runtime-owned layout exclusions in
    ``image_prompt`` (for example, ``Do not create a reference sheet``). Those
    explicit negative constraints remain accepted for backward compatibility and
    must not be confused with a positive request for model-authored layout.
    """
    lowered = prompt.lower()
    leaked: list[str] = []
    for token in CHARACTER_RUNTIME_LAYOUT_TOKENS:
        for match in re.finditer(re.escape(token), lowered):
            clause_start = max(
                lowered.rfind(".", 0, match.start()),
                lowered.rfind(";", 0, match.start()),
                lowered.rfind("!", 0, match.start()),
                lowered.rfind("?", 0, match.start()),
                lowered.rfind("\n", 0, match.start()),
            ) + 1
            prefix = lowered[clause_start:match.start()]
            contrasts = list(_CHARACTER_LAYOUT_CONTRAST_RE.finditer(prefix))
            if contrasts:
                prefix = prefix[contrasts[-1].end():]
            if _CHARACTER_LAYOUT_NEGATION_RE.search(prefix):
                continue
            leaked.append(token)
            break
    return leaked


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
- CHARACTER 的 image_prompt 只描述一个人物的稳定视觉身份：脸型五官、年龄感、发型发色、肤色、体态、基础服装轮廓/材质/颜色和标志性可见特征。不要要求模型自己排版三视图、四视图、reference sheet、contact sheet 或 face close-up。
- CHARACTER 的 image_prompt 与 negative_prompt 都不要出现 multi-panel、turnaround、reference sheet、contact sheet、collage、split screen、front/side/back view、face close-up 等版式词，即使是否定句也不要写；这些词会激活 Z-Image Turbo 的角色设定表先验。Runtime 会自己加入单人朝向约束并负责最终四栏合成。
- CHARACTER 禁止把人物关系、剧情动作、手机等临时道具写成资产身份；除非稳定身份绝对需要，不要加入剧情道具。Runtime 先用 Z-Image 生成唯一正面主身份图，再把正面图作为 Image 1 交给 Qwen Image Edit 2511，按其 Professional Skill 只编辑朝向生成侧面和背面；面部特写直接来自正面主图；Prompt 不负责多面板排版。
- SCENE 只表现稳定环境身份、空间布局、材质、landmarks、光照和色彩，不把剧情中的人物带进环境资产图。
- PROP 只表现稳定物体身份、形态、尺度、材质、颜色和标志性细节，不加入无关人物/场景。
- 当前 Turbo Runtime 使用 zeroed negative conditioning，因此人物/场景/道具的语义排除项（其他人物、临时道具、文字、水印、剧情场景等）必须同时作为 `Do not ...` 约束写进 image_prompt；negative_prompt 也必须返回用于审计。CHARACTER 的版式排除词是唯一例外：不要在 Skill 输出中重复，由 Runtime 自己控制。
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
            "prompt_contract": "replica-assets-zimage-front-qwen-edit-v4",
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
            leaked_layout = _positive_character_layout_tokens(item.image_prompt)
            if leaked_layout:
                raise AppError(
                    "ASSET_IMAGE_CHARACTER_PROMPT_SCOPE_INVALID",
                    "人物 Prompt Skill 只能编译稳定人物身份；三视图和面部特写版式由 Runtime 确定性生成",
                    status_code=502,
                    details={"target_entity_id": entity_id, "runtime_layout_tokens": leaked_layout},
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
