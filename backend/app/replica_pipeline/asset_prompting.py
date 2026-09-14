import json
import re
from dataclasses import dataclass
from typing import Any

from arkruntime import Ark
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import AppError


FLUX_ASSET_PROMPT_CONTRACT = "flux-schnell-asset-reference-v2"
MAX_OUTPUT_TOKENS = 32768


class FluxAssetPromptSemantic(BaseModel):
    target_entity_id: str = Field(min_length=1, max_length=160)
    visual_design_zh: str = Field(min_length=8, max_length=4000)
    visual_facts_en: str = Field(min_length=8, max_length=5000)
    avoid_en: str = Field(min_length=3, max_length=2000)


class FluxAssetPromptBatch(BaseModel):
    items: list[FluxAssetPromptSemantic] = Field(min_length=1, max_length=128)


@dataclass(frozen=True)
class FluxPromptCompileResult:
    specs: list[dict[str, Any]]
    remote_job_id: str | None = None


def _json_object(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("ASSET_PROMPT_PROVIDER_INVALID", "资产图 Prompt Provider 未返回 JSON object", status_code=502)


def _assert_chinese(value: str) -> None:
    if len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value)) < 6:
        raise AppError(
            "ASSET_PROMPT_REVIEW_LANGUAGE_INVALID",
            "资产视觉设计审核说明必须以简体中文为主",
            status_code=502,
        )


def _asset_type_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).upper()


def _provider_prompt(*, specs: list[dict[str, Any]], target_region: str, visual_style: str) -> str:
    source = [
        {
            "target_entity_id": str(item["entity_id"]),
            "asset_type": _asset_type_name(item["asset_type"]),
            "display_name": str(item["display_name"]),
            "localized_review_facts_zh": str(item["review_zh"]),
        }
        for item in specs
    ]
    schema = FluxAssetPromptBatch.model_json_schema()
    return f"""你正在执行 AI Drama Studio 第 3 步资产图的 Flux.1 Schnell 专属 Prompt Compiler。

这一步不是重新写故事，也不是视频提示词。输入事实来自已经人工确认的本土化分镜；你只负责把人物、场景、道具变成可稳定复用的视觉资产设计，并把它整理成适合 Flux.1 Schnell 的图像执行事实。

目标地区：{target_region}
视觉风格：{visual_style}
Prompt contract：{FLUX_ASSET_PROMPT_CONTRACT}

硬规则：
1. items 必须与输入 target_entity_id 一一对应，不能漏项、重复、改 ID、合并或新增实体。
2. visual_design_zh 是给中国用户审核的资产级视觉设计，必须使用简体中文，具体、可视、可复用；不要复述故事情节、对白、镜头节奏或人物关系。
3. visual_facts_en 是给 Flux.1 Schnell 的英文视觉事实，只描述画面中可见的外观、材质、颜色、构图所需的身份特征；不要写抽象剧情、心理活动、对白、运镜或视频动作。
4. 可以把输入里过于抽象的“身份/设定”具体化为稳定视觉方案，但不能改变已经给出的核心身份、地区、时代、职业/功能或显式外观事实。
5. CHARACTER：必须形成单一稳定人物身份，重点具体化年龄感、脸型五官、肤色/妆容（仅在事实允许时）、发型发色、体态、基础服装轮廓/材质/颜色、标志性可见特征。不要设计逐镜换装。
6. SCENE：必须形成空场景视觉基线，重点具体化空间布局、建筑/室内风格、固定地标、材质、色彩、稳定光照；不要加入人物，不要根据剧情擅自发明时间推进。
7. PROP：必须形成单一道具的形态、比例、材质、颜色、尺度和标志性细节；不要加入手、人物或场景剧情。
8. avoid_en 写最重要的视觉排除项。禁止文字、水印、拼图、多格图、重复主体、额外人物/物体、截断主体，以及与当前 asset_type 冲突的元素。
9. 不输出 Markdown、解释或思考过程，只输出符合 JSON Schema 的单个 object。

输入资产：
{json.dumps(source, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


def _compose_execution_prompt(*, asset_type: str, display_name: str, visual_facts_en: str, avoid_en: str, visual_style: str, target_region: str) -> str:
    kind = asset_type.upper()
    if kind == "CHARACTER":
        framing = (
            "Single fictional character production reference image. Exactly one person. Full body from head to shoes fully visible, "
            "neutral relaxed standing pose, front three-quarter view, eye-level camera, natural proportions, 50mm portrait perspective. "
            "Plain seamless light-gray studio background, soft even studio lighting. Preserve one consistent face, hairstyle, body type and base wardrobe."
        )
    elif kind == "SCENE":
        framing = (
            "Empty environment production reference image. No people, no characters. Wide establishing view that clearly shows the stable spatial layout, "
            "architecture, fixed landmarks, materials and lighting baseline. Realistic perspective, coherent scale, production-design reference quality."
        )
    else:
        framing = (
            "Single prop production reference image. Exactly one isolated object, entire object fully visible, centered three-quarter product view, "
            "plain neutral studio background, soft even lighting, clear shape, scale, materials, colors and signature details. No hands and no people."
        )
    return (
        f"{framing} Asset name: {display_name}. Target region context: {target_region}. "
        f"Visual identity facts: {visual_facts_en.strip()} Visual style: {visual_style}. "
        f"Avoid: {avoid_en.strip()} No text, captions, labels, watermark, logo overlay, collage, split screen or contact sheet."
    )


class DoubaoFluxAssetPromptCompiler:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError(
                "ASSET_PROMPT_PROVIDER_NOT_CONFIGURED",
                "火山引擎资产图 Prompt Provider 尚未配置",
                status_code=409,
            )

    def profile(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "CLOUD_API_STRUCTURED_TEXT",
            "prompt_contract": FLUX_ASSET_PROMPT_CONTRACT,
        }

    def compile(
        self,
        *,
        specs: list[dict[str, Any]],
        target_region: str,
        visual_style: str,
    ) -> FluxPromptCompileResult:
        assert self.settings.p7_doubao_api_key is not None
        client = Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _provider_prompt(specs=specs, target_region=target_region, visual_style=visual_style),
                        }
                    ],
                }
            ],
            thinking={"type": "enabled"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "flux_asset_prompt_batch",
                    "schema": FluxAssetPromptBatch.model_json_schema(),
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
        if not text:
            raise AppError("ASSET_PROMPT_PROVIDER_EMPTY", "资产图 Prompt Provider 未返回可用文本", status_code=502)

        try:
            batch = FluxAssetPromptBatch.model_validate_json(_json_object(text))
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "ASSET_PROMPT_PROVIDER_INVALID",
                f"资产图 Prompt Provider 结果未通过数据契约校验（{type(exc).__name__}）",
                status_code=502,
            ) from exc

        expected_ids = [str(item["entity_id"]) for item in specs]
        actual_ids = [item.target_entity_id for item in batch.items]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
            raise AppError(
                "ASSET_PROMPT_PROVIDER_COVERAGE_INVALID",
                "资产图 Prompt Provider 没有完整覆盖本土化分镜中的资产实体",
                status_code=502,
                details={"expected": expected_ids, "actual": actual_ids},
            )

        semantic_by_id = {item.target_entity_id: item for item in batch.items}
        compiled: list[dict[str, Any]] = []
        for source in specs:
            entity_id = str(source["entity_id"])
            semantic = semantic_by_id[entity_id]
            _assert_chinese(semantic.visual_design_zh)
            asset_type = _asset_type_name(source["asset_type"])
            compiled.append(
                {
                    **source,
                    "review_zh": semantic.visual_design_zh.strip(),
                    "prompt": _compose_execution_prompt(
                        asset_type=asset_type,
                        display_name=str(source["display_name"]),
                        visual_facts_en=semantic.visual_facts_en,
                        avoid_en=semantic.avoid_en,
                        visual_style=visual_style,
                        target_region=target_region,
                    ),
                    "negative_prompt": semantic.avoid_en.strip(),
                }
            )
        return FluxPromptCompileResult(
            specs=compiled,
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )
