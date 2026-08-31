"""G2.4：Scene Narrative 的确定性 Source / Support Validator。

Validator 不判断“文采”，只负责硬边界：
- Candidate 必须属于当前 Scene；
- 每个标题/摘要必须引用当前 Grounding Packet 中真实存在的 Fxxxx；
- 不能泄漏内部 P1/P2 引用；普通文本只能使用当前 Scene 已存在的“人物N”；
- 地点/时间/室内外/道具/景别等冻结硬锚点一旦出现在文本中，会确定性补齐对应 support；
- 剧情摘要自动补 Scene 基础摘要与必要的人物存在 support，避免模型漏列 provenance 导致误拒绝；
- 视觉/Timeline 事实可以直接陈述；ASR 只允许作为“说了什么/争论什么/指责什么”的受限 Narrative 来源；
- 摘要若使用仅来自 ASR 的普通词面，所在分句必须有争论/指责/称/表示/质问/回应等对白框架，并补对应 DIALOGUE support；
- 仅来自 ASR 的高影响事件词可以作为明确话题，或位于明确归因分句中；不能脱离归因框架写成客观既成事实；
- 亲属/伴侣等关系称谓仍只能作为话题，不允许借“称/指责”等框架绑定匿名人物身份；
- 对白中的姓名不能被升级成匿名人物身份绑定；
- 中英文数字/数量必须来自最终已补齐的 support，避免模型把“八年”改成“十年”等；
- 场景标题允许少量受控的高层概括词，例如“纠纷/争执/交流”；
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
_CHINESE_NUMBER_WITH_UNIT_RE = re.compile(
    r"[零〇一二两三四五六七八九十百千万亿]+(?:年|月|天|岁|次|个|块|元|小时|分钟|秒|句)"
)
_CLAUSE_SPLIT_RE = re.compile(r"[，,；;。！？!?]+")
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
# 摘要允许少量“组织语言”字符参与 coverage。它们本身不证明具体事实，只避免“双方/紧张/不满”
# 这类合理压缩词把已经有视觉/对白 provenance 的摘要误判为完全不 grounded。
_SUMMARY_ABSTRACTION_CHARS = frozenset(
    "双方两人彼此冲突争执纠纷对话交流对峙争吵质问回应交涉讨论争论矛盾关系紧张不满气氛"
)
# 普通 ASR 内容只有在明确的话语框架里才能成为 Narrative 来源。该列表只证明“这是对白陈述”，
# 不证明对白中的主张客观为真。
_DIALOGUE_REPORTING_MARKERS = (
    "争论",
    "争执",
    "讨论",
    "谈论",
    "谈到",
    "提到",
    "关于",
    "围绕",
    "指责",
    "质问",
    "回应",
    "表示",
    "声称",
    "称",
    "说",
    "认为",
    "抱怨",
    "询问",
    "反驳",
    "否认",
    "解释",
    "批评",
    "埋怨",
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
# 这些词更容易被错误升级成人物关系。它们只能写成“关于丈夫的问题/谈到父亲”等显式话题，
# 不能仅因为前面有“称/指责/质问”就把“丈夫”当作一个已绑定人物称谓。
_RELATION_IDENTITY_TERMS = frozenset(
    {
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
    }
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
_RELATION_TOPIC_PREFIXES = (
    "围绕",
    "关于",
    "谈到",
    "提到",
    "讨论",
    "谈论",
)
_DIALOGUE_TOPIC_SUFFIXES = (
    "话题",
    "问题",
    "一事",
    "事情",
    "事件",
)
_MIN_SUMMARY_CHAR_COVERAGE = 0.50
_MAX_AUTO_DIALOGUE_SUPPORT_FACTS = 24


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
    """人物1/人物2 的编号不是剧情数字；同时检查阿拉伯数字和带单位的中文数量。"""

    scrubbed = _DISPLAY_PERSON_RE.sub("", text)
    values = set(_NUMBER_RE.findall(scrubbed))
    values.update(_CHINESE_NUMBER_WITH_UNIT_RE.findall(scrubbed))
    return values


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


def _dialogue_topic_markers(text: str, term: str) -> set[str]:
    """返回当前 claim 中真正包围该 ASR 关键词的话题标记；空集合表示没有明确话题框架。"""

    markers: set[str] = set()
    is_relation_term = term in _RELATION_IDENTITY_TERMS
    allowed_prefixes = _RELATION_TOPIC_PREFIXES if is_relation_term else _DIALOGUE_TOPIC_PREFIXES
    for match in re.finditer(re.escape(term), text):
        start, end = match.span()
        prefix = text[max(0, start - 12) : start]
        suffix = text[end : min(len(text), end + 10)]
        for marker in allowed_prefixes:
            if marker in prefix:
                markers.add(marker)
        for marker in _DIALOGUE_TOPIC_SUFFIXES:
            marker_pos = suffix.find(marker)
            if marker_pos < 0:
                continue
            # 关系词的后缀必须紧跟该关系词，不能借用后面另一个词的“问题/话题”。
            if is_relation_term and marker_pos > 2:
                continue
            markers.add(marker)
    return markers


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


def _dialogue_reporting_markers(text: str) -> set[str]:
    return {marker for marker in _DIALOGUE_REPORTING_MARKERS if marker in text}


def _reporting_markers_for_term(text: str, term: str) -> set[str]:
    """只看包含该 term 的同一分句，避免借用前后别的分句中的“称/指责”来放行。"""

    markers: set[str] = set()
    for clause in (item.strip() for item in _CLAUSE_SPLIT_RE.split(text)):
        if clause and term in clause:
            markers.update(_dialogue_reporting_markers(clause))
    return markers


def _ground_dialogue_claims(
    packet: SceneGroundingPacketV1,
    text: str,
    support: list[str],
    *,
    already_grounded_chars: set[str],
) -> tuple[set[str], str | None]:
    """为普通 ASR 剧情陈述补 provenance，但要求每个需要 ASR 的分句都明确处于话语框架中。

    这里只把“claim 与相关对白实际重叠的字符”加入 coverage，不会把整段 ASR 变成 lexical authority。
    因而对白可以证明“人物在争论/指责某事”，不能证明该事客观发生。
    """

    dialogue_facts = [fact for fact in packet.facts if fact.kind == "DIALOGUE"]
    if not dialogue_facts:
        return set(), None

    dialogue_chars_by_fact = {
        fact.fact_id: _substantive_chars(fact.text)
        for fact in dialogue_facts
    }
    coverage_chars: set[str] = set()
    auto_support_count = 0

    for clause in (item.strip() for item in _CLAUSE_SPLIT_RE.split(text)):
        if not clause:
            continue
        clause_chars = _substantive_chars(clause)
        if not clause_chars:
            continue
        reporting_markers = _dialogue_reporting_markers(clause)
        marker_chars = _substantive_chars("".join(sorted(reporting_markers)))

        ranked: list[tuple[int, str, set[str]]] = []
        for fact in dialogue_facts:
            overlap = clause_chars.intersection(dialogue_chars_by_fact[fact.fact_id])
            meaningful = overlap.difference(already_grounded_chars)
            meaningful = meaningful.difference(_SUMMARY_ABSTRACTION_CHARS)
            meaningful = meaningful.difference(marker_chars)
            if len(meaningful) >= 2:
                ranked.append((len(meaningful), fact.fact_id, overlap))

        if not ranked:
            continue
        if not reporting_markers:
            return set(), "使用了仅来自对白的内容，但该分句缺少争论/指责/称/表示等对白框架"

        ranked.sort(key=lambda item: (-item[0], item[1]))
        for _score, fact_id, overlap in ranked:
            if auto_support_count >= _MAX_AUTO_DIALOGUE_SUPPORT_FACTS:
                break
            _append_support(support, fact_id)
            auto_support_count += 1
            coverage_chars.update(overlap)
        coverage_chars.update(marker_chars)

    return coverage_chars, None


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

    lexical_support_text = "".join(
        fact.text for fact in supported_facts if fact.kind in _LEXICAL_SOURCE_KINDS
    )
    supported_chars = _substantive_chars(lexical_support_text)
    claim_chars = _substantive_chars(text)

    if field_label == "剧情摘要":
        # 高影响事件词如果来自 ASR，可以是“围绕 X”的话题，也可以位于明确的归因分句中；
        # 但丈夫/妻子等关系称谓仍只允许话题表达，不能借“称/指责”等框架绑定匿名人物身份。
        dialogue_topic_chars: set[str] = set()
        for term in _SENSITIVE_PLOT_TERMS:
            if term not in text or term in lexical_support_text:
                continue
            dialogue_facts = _dialogue_facts_containing(packet, term)
            topic_markers = _dialogue_topic_markers(text, term)
            reporting_markers = (
                set()
                if term in _RELATION_IDENTITY_TERMS
                else _reporting_markers_for_term(text, term)
            )
            accepted_markers = topic_markers.union(reporting_markers)
            if dialogue_facts and accepted_markers:
                for fact in dialogue_facts:
                    _append_support(support, fact.fact_id)
                dialogue_topic_chars.update(_substantive_chars(term))
                for marker in accepted_markers:
                    dialogue_topic_chars.update(_substantive_chars(marker))
                continue
            return None, [
                _claim_warning(
                    packet.scene_ordinal,
                    field_label,
                    f"包含来源未支持的新内容字符/关键剧情词“{term}”或被写成未归因的既成事件/关系",
                )
            ]

        # 普通对白内容也可以进入 Narrative，但必须逐分句处于明确的说话/争论框架中。
        dialogue_claim_chars, dialogue_reason = _ground_dialogue_claims(
            packet,
            text,
            support,
            already_grounded_chars=supported_chars.union(dialogue_topic_chars),
        )
        if dialogue_reason is not None:
            return None, [_claim_warning(packet.scene_ordinal, field_label, dialogue_reason)]

        # 所有自动补齐的 DIALOGUE support 都完成之后再检查数量，避免真实 ASR“八年/一句”被提前误拒；
        # 同时防止模型把来源中的“八年”改成“十年”。
        supported_facts = [fact_by_id[fact_id] for fact_id in support]
        supported_text = " ".join(fact.text for fact in supported_facts)
        unsupported_numbers = sorted(_numeric_literals(text).difference(_numeric_literals(supported_text)))
        if unsupported_numbers:
            return None, [_claim_warning(packet.scene_ordinal, field_label, "包含来源未支持的新数字/数量")]

        if claim_chars:
            coverage_chars = (
                supported_chars
                .union(dialogue_topic_chars)
                .union(dialogue_claim_chars)
                .union(_SUMMARY_ABSTRACTION_CHARS)
            )
            grounded_chars = claim_chars.intersection(coverage_chars)
            coverage = len(grounded_chars) / len(claim_chars)
            if coverage < _MIN_SUMMARY_CHAR_COVERAGE:
                return None, [
                    _claim_warning(
                        packet.scene_ordinal,
                        field_label,
                        f"与来源事实/受限对白陈述的内容覆盖率过低（{coverage:.0%}）",
                    )
                ]
    else:
        supported_text = " ".join(fact.text for fact in supported_facts)
        unsupported_numbers = sorted(_numeric_literals(text).difference(_numeric_literals(supported_text)))
        if unsupported_numbers:
            return None, [_claim_warning(packet.scene_ordinal, field_label, "包含来源未支持的新数字/数量")]

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
