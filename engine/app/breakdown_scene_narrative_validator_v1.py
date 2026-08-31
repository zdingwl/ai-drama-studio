"""G2.4：Scene Narrative 的确定性 Source / Support Validator。

Validator 不判断“文采”，只负责硬边界：
- Candidate 必须属于当前 Scene；
- 每个标题/摘要必须引用当前 Grounding Packet 中真实存在的 Fxxxx；
- 不能泄漏内部 P1/P2 引用；普通文本只能使用当前 Scene 已存在的“人物N”；
- 文本提到某个“人物N”时，其 support facts 中必须至少有一条确实关联该人物；
- 文本直接出现地点/时间/道具/景别等冻结硬锚点时，support 中必须有真正包含该锚点的事实；
- 新标题/摘要的实质字符必须来自所引用的非 ASR/OCR 冻结事实，只放行少量语法连接字；
- 剧情摘要必须至少引用一条 Scene summary / Shot visual / performance / prop interaction 事实，禁止只靠对白猜剧情；
- 禁止 Final Asset / database id 风格的身份声明；
- 任一 claim 失败时只丢弃该 claim，不修改冻结 Timeline。

这是故意保守的 fail-closed validator：宁可拒绝自由改写并回退确定性 Timeline，也不允许
“support id 真实，但文字偷偷加入新动作/姓名/剧情”的伪 grounded 输出。
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
# accepted user prose. This blocks a subtitle/dialogue string from silently becoming an identity claim.
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
# Only grammatical glue is exempt from lexical provenance. Factual direction/time/space characters
# such as 前/后/上/下/内/外 are intentionally NOT exempt.
_GRAMMAR_GLUE_CHARS = frozenset("的了着过在于与和并及其这那此把被为是有又将所个一段里中")


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

    # 对已经存在于冻结 Timeline 的硬词做可判定覆盖检查。比如输出直接写“夜晚客厅”，
    # support 不能只引用“客厅”而不引用任何包含“夜晚”的事实。
    anchors: list[str] = []
    for fact in packet.facts:
        if fact.kind not in _HARD_ANCHOR_KINDS:
            continue
        anchor = fact.text.strip()
        if not anchor or len(anchor) > 120 or anchor in anchors:
            continue
        if anchor in text:
            anchors.append(anchor)
    for anchor in anchors:
        if not any(anchor in fact.text for fact in supported_facts):
            return None, [_claim_warning(packet.scene_ordinal, field_label, f"硬事实“{anchor}”缺少对应 support")]

    # 防止“真实 support id + 新编剧情文字”。只允许 claim 使用其 support 中非 ASR/OCR 事实已经出现的
    # 实质字符；少量语法连接字放行。该规则很保守，合法的自由同义改写也可能被拒绝，但会安全回退。
    lexical_support_text = "".join(
        fact.text for fact in supported_facts if fact.kind in _LEXICAL_SOURCE_KINDS
    )
    supported_chars = _substantive_chars(lexical_support_text)
    claim_chars = _substantive_chars(text)
    novel_chars = sorted(claim_chars.difference(supported_chars))
    if novel_chars:
        preview = "".join(novel_chars[:8])
        return None, [_claim_warning(packet.scene_ordinal, field_label, f"包含来源未支持的新内容字符“{preview}”")]

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
