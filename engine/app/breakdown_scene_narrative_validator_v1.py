"""G2.4：Scene Narrative 的确定性 Source / Support Validator。

Validator 不判断“文采”，只负责硬边界：
- Candidate 必须属于当前 Scene；
- 每个标题/摘要必须引用当前 Grounding Packet 中真实存在的 Fxxxx；
- 不能泄漏内部 P1/P2 引用；普通文本只能使用当前 Scene 已存在的“人物N”；
- 文本提到某个“人物N”时，其 support facts 中必须至少有一条确实关联该人物；
- 地点/时间/室内外/道具/景别等冻结硬锚点一旦出现在文本中，会确定性补齐对应 support；
- 剧情摘要仍使用保守 lexical guard，禁止“真实 support id + 新编动作/姓名/剧情”；
- 场景标题允许少量受控的高层概括词，例如“纠纷/争执/交流”，但不能借 ASR/OCR 引入姓名；
- 新数字必须出现在 support 中，避免凭空增加数量、时间、门牌等事实；
- 禁止 Final Asset / database id 风格的身份声明；
- 任一 claim 失败时只丢弃该 claim，不修改冻结 Timeline。

标题是软 Narrative 标签，允许有限概括；剧情摘要仍然更严格。无论 Narrative 是否通过，
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
# Dialogue/OCR may help the model understand context, but cannot introduce new lexical facts/names into
# accepted summary prose. This blocks a subtitle/dialogue string from silently becoming an identity claim.
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
# Only grammatical glue is exempt from summary lexical provenance. Factual direction/time/space
# characters such as 前/后/上/下/内/外 are intentionally NOT exempt.
_GRAMMAR_GLUE_CHARS = frozenset("的了着过在于与和并及其这那此把被为是有又将所个一段里中")
# 标题是软组织层，允许少量高层概括词；仍禁止任意自由词汇，避免从对白/OCR 偷带姓名。
_TITLE_ABSTRACTION_CHARS = frozenset(
    "冲突争执纠纷对话交流对峙相遇争吵质问回应交涉讨论等待离开回家谈互动矛盾关系"
)


def _claim_warning(scene_ordinal: int, field: str, reason: str) -> str:
    return f"场景 {scene_ordinal} 的 {field} 未通过来源校验：{reason}，已回退为确定性 Timeline 文本"


def _is_han(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _substantive_chars(text: str) -> set[str]:
    """提取用于保守 novelty guard 的内容字符；人物N 由单独 identity guard 处理。"""

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

    display_to_ref = {item.display_name: item.ref for item in packet.people}
    mentioned_people = set(_DISPLAY_PERSON_RE.findall(text))
    unknown_people = mentioned_people.difference(display_to_ref)
    if unknown_people:
        return None, [_claim_warning(packet.scene_ordinal, field_label, "引用了当前 Scene 不存在的人物")]

    # 硬锚点本身已经是冻结事实。模型若在文本中原样用了它但忘了列 support，Validator 可以
    # 无歧义地把对应事实补回，而不是把整段可用文字丢掉。
    for fact in packet.facts:
        if fact.kind not in _HARD_ANCHOR_KINDS:
            continue
        anchor = fact.text.strip()
        if anchor and len(anchor) <= 120 and anchor in text and fact.fact_id not in support:
            support.append(fact.fact_id)

    supported_facts = [fact_by_id[fact_id] for fact_id in support]
    supported_people: set[str] = set()
    for fact in supported_facts:
        supported_people.update(fact.people)
    for display_name in mentioned_people:
        if display_to_ref[display_name] not in supported_people:
            return None, [_claim_warning(packet.scene_ordinal, field_label, f"{display_name} 缺少人物级 support")]

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
        # 摘要仍保持保守：真实 support id 不能成为编造新动作/姓名/剧情的外壳。
        novel_chars = sorted(claim_chars.difference(supported_chars))
        if novel_chars:
            preview = "".join(novel_chars[:8])
            return None, [_claim_warning(packet.scene_ordinal, field_label, f"包含来源未支持的新内容字符“{preview}”")]
    else:
        # 标题允许有限的剧情抽象，例如“走廊纠纷”。超出来源字符 + 白名单抽象字符仍拒绝，
        # 因此 ASR/OCR 里的姓名不会因为标题权限放宽而自动进入用户结果。
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
