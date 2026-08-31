"""Evidence-gated Window subject-hint resolver for compact Exact-Shot observations.

Window subject hints are soft continuity evidence. A listed Shot ordinal means only that the Window
model believes the anonymous person may appear there; it is not proof that the only visible person
in that Shot is the hinted person.

The legacy resolver accepted a single visible candidate unconditionally. Compact production exposed
that failure mode: a "white off-shoulder woman" hint could bind a gray-hoodie man in a one-person
Shot, and the resulting Stage1 soft edge polluted the whole anonymous continuity graph.

This resolver keeps frozen Shot-local observations authoritative. It resolves ordinal-only Window
hints only when the Exact-Shot appearance provides positive stable support. Short compact aliases
such as ``灰衣``/``灰卫衣`` and ``白露肩装`` are normalized locally for hint matching; this does not
change Character identity rules or the general E6 appearance thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_fusion_replay_v2 as replay_v2
from engine.app import breakdown_p2_fusion_episode_v4 as e4

POLICY = "window-hint-positive-appearance-support-compact-alias-v2"
MIN_MULTI_CANDIDATE_MARGIN = 0.75

_AGE_GROUPS = {
    "young": ("年轻", "青年", "少女", "年轻女性", "年轻男子"),
    "old": ("老年", "老妇", "老太太", "老人", "年长"),
}
_HAIR_COLOR_GROUPS = {
    "dark": ("黑发", "黑色头发", "深色长发", "黑长发", "黑发长发", "黑发长直"),
    "gray": ("灰发", "灰白", "白发", "银发"),
}
_ATTIRE_COLOR_GROUPS = {
    "white": ("白色上衣", "白上衣", "白衣", "白衬衫", "白色衬衫", "白露肩", "白色露肩", "白裤", "白色裤"),
    "gray": ("灰色连帽衫", "灰连帽衫", "灰色卫衣", "灰卫衣", "灰衣", "灰色上衣", "灰上衣"),
    "black": ("黑色上衣", "黑上衣", "黑衣"),
    "orange": ("橙色", "橘色"),
    "beige": ("米色", "卡其色"),
}
_ATTIRE_DETAIL_GROUPS = {
    "offshoulder": ("露肩上衣", "露肩装", "露肩"),
    "hoodie": ("连帽衫", "卫衣"),
    "floral": ("花衬衫", "花卉", "花纹衬衫", "印花衬衫", "印花"),
    "shirt": ("衬衫",),
    "pants": ("裤", "长裤", "阔腿裤"),
}


@dataclass(frozen=True)
class HintSignature:
    gender: str | None
    ages: frozenset[str]
    hair_lengths: frozenset[str]
    hair_colors: frozenset[str]
    attire_colors: frozenset[str]
    attire_details: frozenset[str]


def _group_hits(text: str, groups: Mapping[str, Sequence[str]]) -> frozenset[str]:
    return frozenset(
        name
        for name, tokens in groups.items()
        if any(token in text for token in tokens)
    )


def _signature(value: Any) -> HintSignature:
    text = " ".join(str(value or "").strip().split())
    return HintSignature(
        gender=e4._gender(text),
        ages=_group_hits(text, _AGE_GROUPS),
        hair_lengths=replay_v2._hair_length_classes(text),
        hair_colors=_group_hits(text, _HAIR_COLOR_GROUPS),
        attire_colors=_group_hits(text, _ATTIRE_COLOR_GROUPS),
        attire_details=_group_hits(text, _ATTIRE_DETAIL_GROUPS),
    )


def _explicit_signature_conflict(left: HintSignature, right: HintSignature) -> bool:
    if left.gender and right.gender and left.gender != right.gender:
        return True
    if left.ages and right.ages and left.ages.isdisjoint(right.ages):
        return True
    if "LONG" in left.hair_lengths and right.hair_lengths.intersection({"SHORT", "BALD"}):
        return True
    if "LONG" in right.hair_lengths and left.hair_lengths.intersection({"SHORT", "BALD"}):
        return True
    return False


def _match_score(hint_appearance: Any, observation_appearance: Any) -> tuple[float, int]:
    hint = _signature(hint_appearance)
    observation = _signature(observation_appearance)
    if _explicit_signature_conflict(hint, observation):
        return -math.inf, 0

    score = 0.0
    support = 0

    # Gender can help rank candidates but is never sufficient by itself: two different women/men
    # may share one Scene. At least one non-gender stable cue is required below.
    if hint.gender and observation.gender and hint.gender == observation.gender:
        score += 0.5

    shared_ages = hint.ages.intersection(observation.ages)
    if shared_ages:
        score += 1.25
        support += 1

    shared_hair_lengths = hint.hair_lengths.intersection(observation.hair_lengths)
    if shared_hair_lengths:
        score += 1.5
        support += 1

    shared_hair_colors = hint.hair_colors.intersection(observation.hair_colors)
    if shared_hair_colors:
        score += 1.25
        support += 1

    shared_attire_colors = hint.attire_colors.intersection(observation.attire_colors)
    if shared_attire_colors:
        score += 1.75
        support += 1

    shared_attire_details = hint.attire_details.intersection(observation.attire_details)
    for detail in shared_attire_details:
        # Generic shirt/pants is weaker than distinctive off-shoulder/hoodie/floral structure.
        if detail in {"shirt", "pants"}:
            score += 0.5
        else:
            score += 2.0
            support += 1

    # Preserve useful evidence from the accepted generic matcher, but compact alias support above is
    # what makes abbreviated observations usable. Generic similarity alone cannot create support.
    generic_score, generic_strong = e4._appearance_similarity(hint_appearance, observation_appearance)
    if math.isfinite(generic_score):
        score += min(2.0, max(0.0, float(generic_score)) * 0.25)
        if generic_strong >= 2:
            support += 1

    return score, support


def resolve_hint_nodes(
    hint: Mapping[str, Any],
    observations: Sequence[e4.SubjectObservation],
    index_by_node: Mapping[tuple[str, str], int],
) -> list[int]:
    """Resolve one Window hint without assuming listed Shot ordinals guarantee presence.

    Explicit ``members`` remain highest-confidence compatibility evidence. Ordinal-only hints are
    filtered per Shot by positive Exact-Shot appearance support. A one-person Shot is therefore not
    auto-accepted merely because no alternative candidate exists.
    """

    result: list[int] = []
    raw_members = hint.get("members")
    if isinstance(raw_members, list):
        for raw in raw_members:
            if not isinstance(raw, Mapping):
                continue
            key = (
                str(raw.get("revision_item_id") or "").strip(),
                str(raw.get("label") or "").strip(),
            )
            index = index_by_node.get(key)
            if index is not None and index not in result:
                result.append(index)
        if len(result) >= 2:
            return result

    raw_ordinals = hint.get("shot_ordinals")
    if not isinstance(raw_ordinals, list):
        return result
    appearance = " ".join(str(hint.get("appearance_summary") or "").strip().split())
    if not appearance:
        return result
    try:
        ordinals = {int(value) for value in raw_ordinals}
    except (TypeError, ValueError):
        ordinals = set()

    for ordinal in sorted(ordinals):
        candidates = [
            (index, item)
            for index, item in enumerate(observations)
            if item.shot_ordinal == ordinal
        ]
        if not candidates:
            continue

        scored: list[tuple[float, int, int]] = []
        for index, item in candidates:
            score, support = _match_score(appearance, item.appearance_summary)
            scored.append((score, support, index))
        scored.sort(key=lambda row: (row[0], row[1], -row[2]), reverse=True)

        if not scored:
            continue
        best_score, best_support, best_index = scored[0]
        if not math.isfinite(best_score) or best_support < 1:
            continue

        if len(scored) > 1:
            second_score = scored[1][0]
            if math.isfinite(second_score) and best_score - second_score < MIN_MULTI_CANDIDATE_MARGIN:
                continue

        if best_index not in result:
            result.append(best_index)

    return result


__all__ = [
    "MIN_MULTI_CANDIDATE_MARGIN",
    "POLICY",
    "resolve_hint_nodes",
]
