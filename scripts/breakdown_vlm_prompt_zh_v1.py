"""Simplified-Chinese text profile for Breakdown P2.4 Qwen3-VL semantics.

The structural JSON contract remains unchanged. Only VLM-generated natural-language
fields are required to use Simplified Chinese. Machine keys/enums and shot-local
``subject_A`` labels stay stable so the frozen Provider/Fusion contracts do not change.
ASR dialogue and OCR text remain separate raw evidence and are never translated here.
"""
from __future__ import annotations

from typing import Any, Mapping

PROMPT_PROFILE = "breakdown-p2-vlm-zh-draft-v1"
DRAFT_TEXT_LANGUAGE = "zh-CN"
MIN_CHINESE_FIELD_RATIO = 0.60


def build_prompt(source_language: str) -> str:
    language = (source_language or "und").strip() or "und"
    return f"""你是一名专业的短剧镜头拉片分析师。
只分析这个单独 Reference Clip 中能够被画面直接支持的内容。
项目原始语言是 {language}，它只用于理解项目上下文，不决定 Draft 文案语言。

【输出语言强制规则】
1. 所有由 VLM 生成的自然语言描述字段必须使用简体中文（zh-CN），不要输出英文描述句子。
2. 必须使用简体中文的字段包括：
   - scene.location_hint、scene.time_of_day、scene.environment_description；
   - shot.summary、shot.visual_description、shot.shot_type_hint、shot.camera_motion_hint、shot.narrative_function_hint、shot.composition_hint；
   - subjects[].appearance_summary、subjects[].activity_summary、subjects[].screen_position；
   - events[].content；
   - props[].label、props[].narrative_reason。
3. JSON key、subject_A/subject_B 这类匿名标签、数字，以及下列机器枚举必须严格保持英文 token，不能翻译：
   - interior_exterior: INT|EXT|MIXED|UNKNOWN
   - visibility: FULL|PARTIAL|OCCLUDED|UNKNOWN
   - speaking_state: LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN
   - event_type: VISUAL|ACTION
   - importance: LOW|MEDIUM|HIGH
4. scene.time_of_day 优先使用稳定中文词：白天、夜晚、清晨、黄昏；无法判断时写“未知”或留空。
5. subjects[].screen_position 优先使用稳定中文词：左侧、中央、右侧、前景、背景；无法判断时写“未知”或留空。

【用于 Fusion 的稳定措辞规则】
1. scene.location_hint 必须是简短、通用、稳定的地点类别，不要写长句，不要凭想象加具体店名/酒店名/房间号。例如只看得出走廊就写“走廊”，只看得出客厅就写“客厅”。
2. 同类可见场景尽量使用同一个中文地点词，避免“走廊 / 室内走廊 / 酒店走廊”这类无证据的措辞漂移。
3. subjects[].appearance_summary 使用稳定顺序描述最有区分度的可见特征：发型/头部特征 → 上衣颜色与款式 → 下装 → 显著配饰或手持物。保持客观、简洁，不用修辞，不写动作。
4. subjects[].activity_summary 只写当前动作，不重复外观信息。
5. props[].label 使用简短稳定的中文名词，例如“黑色塑料袋”“手机”“蓝色玫瑰”，不要写成完整句子。
6. shot_type_hint 和 camera_motion_hint 使用短中文术语，例如“特写 / 中景 / 全景”“静止 / 推近 / 拉远 / 跟拍”，不要写解释性长句。

【视觉事实边界】
1. 不要猜测真实姓名、全局身份、Character ID、Scene ID、Prop ID 或任何业务/数据库 ID。
2. 人物只在当前镜头内匿名编号，按稳定视觉顺序使用 subject_A、subject_B、subject_C……。
3. 不要转录对白、字幕、招牌、手机屏幕、文件或其他可读文字；ASR/OCR 是独立 Provider。
4. speaking_state 只能表示基于嘴部/身体互动的视觉提示，不是真实 Speaker 身份结论。
5. 只保留与剧情或人物互动有关的道具，不要罗列所有背景物体。
6. event 的 start_ratio/end_ratio 必须是相对当前片段 0 到 1 的归一化比例，不要编造源视频绝对时间。
7. 不确定时使用 UNKNOWN、中文“未知”或留空，不要靠想象补全。
8. 只返回一个 JSON object，JSON 外不要输出任何解释性文字。

JSON schema:
{{
  "scene": {{
    "location_hint": "简体中文稳定地点短语或空字符串",
    "interior_exterior": "INT|EXT|MIXED|UNKNOWN",
    "time_of_day": "简体中文时间提示或空字符串",
    "environment_description": "简体中文环境描述或空字符串"
  }},
  "shot": {{
    "summary": "简体中文镜头核心内容摘要",
    "visual_description": "简体中文可见构图与动作描述",
    "shot_type_hint": "简体中文短景别术语或空字符串",
    "camera_motion_hint": "简体中文短运镜术语或空字符串",
    "narrative_function_hint": "简体中文叙事功能提示或空字符串",
    "composition_hint": "简体中文构图提示或空字符串"
  }},
  "subjects": [
    {{
      "label": "subject_A",
      "appearance_summary": "按稳定特征顺序编写的简体中文可见外观描述",
      "activity_summary": "简体中文当前可见动作描述",
      "screen_position": "简体中文画面位置或空字符串",
      "visibility": "FULL|PARTIAL|OCCLUDED|UNKNOWN",
      "speaking_state": "LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN"
    }}
  ],
  "events": [
    {{
      "event_type": "VISUAL|ACTION",
      "start_ratio": 0.0,
      "end_ratio": 1.0,
      "content": "简体中文可见事件描述",
      "subject_labels": ["subject_A"]
    }}
  ],
  "props": [
    {{
      "label": "简体中文稳定道具名词",
      "importance": "LOW|MEDIUM|HIGH",
      "narrative_reason": "简体中文说明它为何与当前可见剧情/互动相关",
      "subject_labels": ["subject_A"]
    }}
  ]
}}
"""


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _contains_han(value: Any) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in _text(value))


def _natural_language_fields(semantic: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    scene = semantic.get("scene")
    if isinstance(scene, Mapping):
        for key in ("location_hint", "time_of_day", "environment_description"):
            text = _text(scene.get(key))
            if text:
                values.append(text)

    shot = semantic.get("shot")
    if isinstance(shot, Mapping):
        for key in (
            "summary",
            "visual_description",
            "shot_type_hint",
            "camera_motion_hint",
            "narrative_function_hint",
            "composition_hint",
        ):
            text = _text(shot.get(key))
            if text:
                values.append(text)

    subjects = semantic.get("subjects")
    if isinstance(subjects, list):
        for subject in subjects:
            if not isinstance(subject, Mapping):
                continue
            for key in ("appearance_summary", "activity_summary", "screen_position"):
                text = _text(subject.get(key))
                if text:
                    values.append(text)

    events = semantic.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, Mapping):
                text = _text(event.get("content"))
                if text:
                    values.append(text)

    props = semantic.get("props")
    if isinstance(props, list):
        for prop in props:
            if not isinstance(prop, Mapping):
                continue
            for key in ("label", "narrative_reason"):
                text = _text(prop.get(key))
                if text:
                    values.append(text)
    return values


def validate_semantic_language(semantic: Mapping[str, Any]) -> dict[str, float | int | str]:
    """Fail closed when Qwen ignores the Simplified-Chinese Draft policy.

    High-value Shot prose is required to contain Han characters whenever present.
    Across all non-empty natural-language fields, at least 60% must contain Han
    characters once there are three or more fields. This tolerates unavoidable
    Latin brand names while preventing an English Draft from reaching Fusion.
    """

    shot = semantic.get("shot")
    if isinstance(shot, Mapping):
        for key in ("summary", "visual_description"):
            text = _text(shot.get(key))
            if text and not _contains_han(text):
                raise ValueError(
                    f"VLM Draft language validation failed: shot.{key} is not Simplified Chinese"
                )

    fields = _natural_language_fields(semantic)
    chinese_fields = sum(1 for value in fields if _contains_han(value))
    ratio = chinese_fields / len(fields) if fields else 1.0
    if len(fields) >= 3 and ratio < MIN_CHINESE_FIELD_RATIO:
        raise ValueError(
            "VLM Draft language validation failed: "
            f"Chinese field ratio {ratio:.2f} < {MIN_CHINESE_FIELD_RATIO:.2f}"
        )
    return {
        "prompt_profile": PROMPT_PROFILE,
        "draft_text_language": DRAFT_TEXT_LANGUAGE,
        "natural_language_field_count": len(fields),
        "chinese_field_count": chinese_fields,
        "chinese_field_ratio": round(ratio, 4),
    }


def install() -> None:
    """Install this prompt into the production runner module before inference."""

    import run_breakdown_vlm_qwen3 as base

    base._prompt = build_prompt
