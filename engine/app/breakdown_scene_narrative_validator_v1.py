"""G2.4：Scene Narrative 的确定性 Source / Support Validator。

Validator 不判断“文采”，只负责硬边界：
- Candidate 必须属于当前 Scene；
- 每个标题/摘要必须引用当前 Grounding Packet 中真实存在的 Fxxxx；
- 不能泄漏内部 P1/P2 引用；普通文本只能使用当前 Scene 已存在的“人物N”；
- 地点/时间/室内外/道具/景别等冻结硬锚点一旦出现在文本中，会确定性补齐对应 support；
- 剧情摘要自动补 Scene 基础摘要与必要的人物存在 support，避免模型漏列 provenance 导致误拒绝；
- 摘要允许有限自然语言压缩，但整体内容必须主要覆盖冻结事实；
- ASR 可以支持“谈到/围绕/讨论某剧情话题”，但不能把对白中的姓名/关系直接绑定成匿名人物身份；
- 高影响剧情词如果只来自 ASR，只允许作为明确的“话题表达”，不能写成已经发生的视觉事件；
- 场景标题允许少量受控的高层概括词，例如“纠纷/争执/交流”；
- 新数字必须出现在 support 中，避免凭空增加数量、时间、门牌等事实；
- 禁止 Final Asset / database id 风格的身份声明；
- 任一 claim 失败时只丢弃该 claim，不修改冻结 Timeline。

标题是软 Narrative 标签；摘要允许受控概括但仍 fail closed。无论 Narrative 是否通过，
Shot/人物/对白/OCR/道具/镜头语言等冻结事实都不由本 Validator 或 LLM 改写。
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from engine.app.breakdown_scene_narrative_contract_v1 import (
    SceneGroundingPacketV1,
    SceneNarrativeCandidateV1,
    SceneNarrativeClaimV1,
    SceneNarrativeSceneV1,
)


class SceneNarrativeValidationError(ValueError):
    """Narrative overlay 与冻结 source anchor 不一致等不可降级结构错误。"""


_INTERNAL_PERSON_REF_RE = re.compile(r"(?<![A-Za-z0-9_])P[1-9][0-9]*(?![A-Za-z0-9_])")
_DISPLAY_PERSON_RE = re.compile(r"人物[1-9][0-9]*")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_DIALOGUE_IDENTITY_NAME_RE = re.compile(
    r"(?:改名成|名字是|名叫|叫|我是|他是|她是)\s*([\u4e00-\u9fff]{2,4})"
)
_FORBIDDEN_IDENTITY_MARKERS = (
    "character_id",
    "scene_id",
    "prop_id",
    "final character",
    "final scene",
    "final prop",
    "角色id",
    "场景id",
    "道具id",
)
_HARD_ANCHOR_KINDS = {
    "SCENE_LOCATION",
    "SCENE_SPACE",
    "SCENE_TIME",
    "PROP",
    "SHOT_TYPE",
    "CAMERA_MOTION",
}
_LEXICAL_SOURCE_KINDS = {
    "SCENE_LOCATION",
    "SCENE_SPACE",
    "SCENE_TIME",
    "SCENE_ENVIRONMENT",
    "SCENE_BASE_SUMMARY",
    "PERSON_APPEARANCE",
    "SHOT_VISUAL",
    "SHOT_PERFORMANCE",
    "PROP",
    "PROP_INTERACTION",
    "SHOT_TYPE",
    "COMPOSITION",
    "CAMERA_MOTION",
}
_NARRATIVE_SOURCE_KINDS = {
    "SCENE_BASE_SUMMARY",
    "SHOT_VISUAL",
    "SHOT_PERFORMANCE",
    "PROP_INTERACTION",
}
_PERSON_SUPPORT_PRIORITY = (
    "PERSON_APPEARANCE",
    "SHOT_VISUAL",
    "SHOT_PERFORMANCE",
    "DIALOGUE",
)
_GRAMMAR_GLUE_CHARS = frozenset("的了着过在于与和并及其这那此把被为是有又将所个一段里中")
_TITLE_ABSTRACTION_CHARS = frozenset(
    "冲突争执纠纷对话交流对峙相遇争吵质问回应交涉讨论等待离开回家谈互动矛盾关系"
)
_SENSITIVE_PLOT_TERMS = (
    "杀死",
    "杀害",
    "死亡",
    "自杀",
    "跳楼",
    "刺伤",
    "砍伤",
    "枪击",
    "开枪",
    "爆炸",
    "绑架",
    "抢劫",
    "强奸",
    "下毒",
    "毒死",
    "火灾",
    "车祸",
    "撞车",
    "逮捕",
    "报警",
    "失踪",
    "住院",
    "手术",
    "怀孕",
    "生子",
    "结婚",
    "离婚",
    "亲吻",
    "接吻",
    "丈夫",
    "妻子",
    "老公",
    "老婆",
    "父亲",
    "母亲",
    "爸爸",
    "妈妈",
    "儿子",
    "女儿",
    "情人",
    "恋人",
    "男友",
    "女友",
    "刀",
    "枪",
    "毒药",
)
_DIALOGUE_TOPIC_PREFIXES = (
    "围绕",
    "关于",
    "谈到",
    "提到",
    "讨论",
    "谈论",
    "询问",
    "质问",
    "争论",
    "争执",
)
_DIALOGUE_TOPIC_SUFFIXES = (
    "话题",
    "问题",
    "一事",
    "事情",
)
_MIN_SUMMARY_CHAR_COVERAGE = 0.50


def _claim_warning(scene_ordinal: int, field: str, reason: str) -> str:
    return f"场景 {scene_ordinal} 的 {field} 未通过来源校验：{reason}，已回退为确定性 Timeline 文本"


def _is_han(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _substantive_chars(text: str) -> set[str]:
    """提取用于保守 novelty/coverage guard 的内容字符；人物N 由 identity guard 单独处理。"""

    scrubbed = _DISPLAY_PERSON_RE.sub("", text.casefold())
    result: set[str] = set()
    for char in scrubbed:
        if char in _GRAMMAR_GLUE_CHARS:
            continue
        if _is_han(char) or char.isalnum():
            result.add(char)
    return result


def _numeric_literals(text: str) -> set[str]:
    """人物1/人物2 的编号不是剧情数字，不参与新数字事实检查。"""

    return set(_NUMBER_RE.findall(_DISPLAY_PERSON_RE.sub("", text)))


def _append_support(support: list[str], fact_id: str) -> None:
    if fact_id not in support:
        support.append(fact_id)


def _first_person_support_fact(packet: SceneGroundingPacketV1, person_ref: str):
    """为已确认属于当前 Scene 的人物补一个最保守的存在性 provenance。"""

    for kind in _PERSON_SUPPORT_PRIORITY:
        for fact in packet.facts:
            if fact.kind == kind and person_ref in fact.people:
                return fact
    for fact in packet.facts:
        if person_ref in fact.people:
            return fact
    return None


def _dialogue_facts_containing(packet: SceneGroundingPacketV1, term: str):
    return [fact for fact in packet.facts if fact.kind == "DIALOGUE" and term in fact.text]


def _is_dialogue_topic_expression(text: str, term: str) -> bool:
    """只允许把对白里的高影响词写成“讨论某话题”，不能写成事件已经发生。"""

    for match in re.finditer(re.escape(term), text):
        start, end = match.span()
        prefix = text[max(0, start - 10) : start]
        suffix = text[end : min(len(text), end + 8)]
        if any(marker in prefix for marker in _DIALOGUE_TOPIC_PREFIXES):
            return True
        if any(marker in suffix for marker in _DIALOGUE_TOPIC_SUFFIXES):
            return True
    return False


def _dialogue_identity_names(packet: SceneGroundingPacketV1) -> set[str]:
    """从对白中的显式身份/改名句抽取候选姓名；这些词不能进入匿名人物 Narrative。"""

    names: set[str] = set()
    for fact in packet.facts:
        if fact.kind != "DIALOGUE":
            continue
        for match in _DIALOGUE_IDENTITY_NAME_RE.finditer(fact.text):
            name = match.group(1).strip()
            if name:
                names.add(name)
    return names


def _validate_claim(
    packet: SceneGroundingPacketV1,
    claim: SceneNarrativeClaimV1 | None,
    *,
    field_label: str,
) -> tuple[SceneNarrativeClaimV1 | None, list[str]]:
    if claim is None:
        return None, []

    fact_by_id = {item.fact_id: item for item in packet.facts}
    support: list[str] = []
    for fact_id in claim.support:
        if fact_id not in support:
            support.append(fact_id)
    if not support:
        return None, [_claim_warning(packet.scene_ordinal, field_label, "support 为空")]
    missing = [fact_id for fact_id in support if fact_id not in fact_by_id]
    if missing:
        return None, [_claim_warning(packet.scene_ordinal, field_label, "引用了不存在的事实")]

    text = claim.text
    if _INTERNAL_PERSON_REF_RE.search(text):
        return None, [_claim_warning(packet.scene_ordinal, field_label, "包含内部 P* 人物引用")]

    lowered = text.casefold()
    if any(marker in lowered for marker in _FORBIDDEN_IDENTITY_MARKERS):
        return None, [_claim_warning(packet.scene_ordinal, field_label, "包含 Final Asset / ID 身份声明")]

    leaked_dialogue_names = sorted(name for name in _dialogue_identity_names(packet) if name in text)
    if leaked_dialogue_names:
        return None, [_claim_warning(packet.scene_ordinal, field_label, "包含对白中的未绑定姓名")]

    display_to_ref = {item.display_name: item.ref for item in packet.people}
    mentioned_people = set(_DISPLAY_PERSON_RE.findall(text))
    unknown_people = mentioned_people.difference(display_to_ref)
    if unknown_people:
        return None, [_claim_warning(packet.scene_ordinal, field_label, "引用了当前 Scene 不存在的人物")]

    if field_label == "剧情摘要":
        for fact in packet.facts:
            if fact.kind == "SCENE_BASE_SUMMARY":
                _append_support(support, fact.fact_id)
                break

    for fact in packet.facts:
        if fact.kind not in _HARD_ANCHOR_KINDS:
            continue
        anchor = fact.text.strip()
        if anchor and len(anchor) <= 120 and anchor in text:
            _append_support(support, fact.fact_id)

    supported_people: set[str] = set()
    for fact_id in support:
        supported_people.update(fact_by_id[fact_id].people)
    for display_name in sorted(mentioned_people):
        ref = display_to_ref[display_name]
        if ref in supported_people:
            continue
        person_fact = _first_person_support_fact(packet, ref)
        if person_fact is None:
            return None, [_claim_warning(packet.scene_ordinal, field_label, f"{display_name} 缺少人物级 support")]
        _append_support(support, person_fact.fact_id)
        supported_people.update(person_fact.people)

    supported_facts = [fact_by_id[fact_id] for fact_id in support]
    if field_label == "剧情摘要" and not any(
        fact.kind in _NARRATIVE_SOURCE_KINDS for fact in supported_facts
    ):
        return None, [_claim_warning(packet.scene_ordinal, field_label, "缺少剧情/画面/动作类 support")]

    supported_text = " ".join(fact.text for fact in supported_facts)
    unsupported_numbers = sorted(_numeric_literals(text).difference(_numeric_literals(supported_text)))
    if unsupported_numbers:
        return None, [_claim_warning(packet.scene_ordinal, field_label, "包含来源未支持的新数字")]

    lexical_support_text = "".join(
        fact.text for fact in supported_facts if fact.kind in _LEXICAL_SOURCE_KINDS
    )
    supported_chars = _substantive_chars(lexical_support_text)
    claim_chars = _substantive_chars(text)

    if field_label == "剧情摘要":
        for term in _SENSITIVE_PLOT_TERMS:
            if term not in text or term in lexical_support_text:
                continue
            dialogue_facts = _dialogue_facts_containing(packet, term)
            if dialogue_facts and _is_dialogue_topic_expression(text, term):
                for fact in dialogue_facts:
                    _append_support(support, fact.fact_id)
                continue
            return None, [
                _claim_warning(
                    packet.scene_ordinal,
                    field_label,
                    f"包含来源未支持的新内容字符/关键剧情词“{term}”或被写成既成事件",
                )
            ]

        # 高影响词可能确定性补入 ASR support；重新构造 supported_facts，供最终 provenance 使用。
        supported_facts = [fact_by_id[fact_id] for fact_id in support]
        if claim_chars:
            grounded_chars = claim_chars.intersection(supported_chars)
            coverage = len(grounded_chars) / len(claim_chars)
            if coverage < _MIN_SUMMARY_CHAR_COVERAGE:
                return None, [
                    _claim_warning(
                        packet.scene_ordinal,
                        field_label,
                        f"与来源事实的内容覆盖率过低（{coverage:.0%}）",
                    )
                ]
    else:
        allowed_title_chars = supported_chars.union(_TITLE_ABSTRACTION_CHARS)
        novel_chars = sorted(claim_chars.difference(allowed_title_chars))
        if novel_chars:
            preview = "".join(novel_chars[:8])
            return None, [_claim_warning(packet.scene_ordinal, field_label, f"包含来源未支持的新标题字符“{preview}”")]

    accepted = SceneNarrativeClaimV1(text=text, support=support)
    return accepted, []


def validate_scene_narrative_v1(
    grounding_packet: Mapping[str, Any] | SceneGroundingPacketV1,
    candidate_payload: Mapping[str, Any] | SceneNarrativeCandidateV1,
) -> tuple[dict[str, Any], list[str]]:
    """校验一个 Scene 候选；坏 claim 局部丢弃，Scene/source mismatch 则 fail closed。"""

    packet = (
        grounding_packet
        if isinstance(grounding_packet, SceneGroundingPacketV1)
        else SceneGroundingPacketV1.model_validate(grounding_packet)
    )
    candidate = (
        candidate_payload
        if isinstance(candidate_payload, SceneNarrativeCandidateV1)
        else SceneNarrativeCandidateV1.model_validate(candidate_payload)
    )
    if candidate.scene_ordinal != packet.scene_ordinal:
        raise SceneNarrativeValidationError("Narrative scene_ordinal 与 Grounding Packet 不一致")

    title, title_warnings = _validate_claim(packet, candidate.readable_title, field_label="场景标题")
    summary, summary_warnings = _validate_claim(packet, candidate.story_summary, field_label="剧情摘要")
    warnings = [*title_warnings, *summary_warnings]
    accepted = SceneNarrativeSceneV1(
        scene_ordinal=packet.scene_ordinal,
        source_fingerprint=packet.source_fingerprint,
        readable_title=title,
        story_summary=summary,
    )
    return accepted.model_dump(mode="json"), warnings


__all__ = [
    "SceneNarrativeValidationError",
    "validate_scene_narrative_v1",
]
