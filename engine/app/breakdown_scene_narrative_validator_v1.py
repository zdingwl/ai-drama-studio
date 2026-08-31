"""G2.4：Scene Narrative 的确定性 Source / Support Validator。

Validator 不判断“文采”，只负责硬边界：
- Candidate 必须属于当前 Scene；
- 每个标题/摘要必须引用当前 Grounding Packet 中真实存在的 Fxxxx；
- 不能泄漏内部 P1/P2 引用；普通文本只能使用当前 Scene 已存在的“人物N”；
- 文本提到某个“人物N”时，其 support facts 中必须至少有一条确实关联该人物；
- 禁止 Final Asset / database id 风格的身份声明；
- 任一 claim 失败时只丢弃该 claim，不修改冻结 Timeline。

support refs 是 provenance guard，不是另一个 LLM，也不宣称能做完整自然语言蕴含证明。
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


def _claim_warning(scene_ordinal: int, field: str, reason: str) -> str:
    return f"场景 {scene_ordinal} 的 {field} 未通过来源校验：{reason}，已回退为确定性 Timeline 文本"


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

    supported_people: set[str] = set()
    for fact_id in support:
        supported_people.update(fact_by_id[fact_id].people)
    for display_name in mentioned_people:
        if display_to_ref[display_name] not in supported_people:
            return None, [_claim_warning(packet.scene_ordinal, field_label, f"{display_name} 缺少人物级 support")]

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
