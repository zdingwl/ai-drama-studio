"""Canonicalize compact Exact-Shot appearance aliases for anonymous-continuity matching only.

Compact Exact-Shot v3 intentionally emits short reconstruction-safe descriptions. Those short forms
can be semantically equivalent to the older verbose appearance phrases while missing tokens used by
the accepted continuity feature extractor (for example ``灰卫衣`` vs ``灰色连帽衫``).

This helper is deliberately narrow: it does not change persisted VLM evidence, Final Character
identity, Shot-local labels, or any merge threshold. It only provides a canonical comparison view for
read-only/anonymous continuity stages after Window hint resolution.
"""
from __future__ import annotations

from typing import Sequence

from engine.app import breakdown_p2_fusion_episode_v4 as e4

POLICY = "compact-observation-stable-alias-normalization-v1"

_REPLACEMENTS = (
    ("白色露肩装", "白色露肩上衣"),
    ("白露肩装", "白色露肩上衣"),
    ("灰色卫衣", "灰色连帽衫"),
    ("灰卫衣", "灰色连帽衫"),
    ("灰连帽衫", "灰色连帽衫"),
    ("白衬衣", "白色衬衫"),
    ("灰发卷曲", "灰发卷发"),
    ("露肩装", "露肩上衣"),
    ("卫衣", "连帽衫"),
    ("灰衣", "灰色上衣"),
    ("白衣", "白色上衣"),
)


def normalize_appearance(value: str) -> str:
    """Return a comparison-only canonical phrase without changing source evidence."""

    text = "".join(str(value or "").strip().split())
    for source, target in _REPLACEMENTS:
        text = text.replace(source, target)
    return text


def normalize_observations(
    observations: Sequence[e4.SubjectObservation],
) -> list[e4.SubjectObservation]:
    """Create index-aligned observations whose appearance text is canonicalized for matching."""

    return [
        e4.SubjectObservation(
            shot_revision_item_id=item.shot_revision_item_id,
            shot_ordinal=item.shot_ordinal,
            label=item.label,
            appearance_summary=normalize_appearance(item.appearance_summary),
        )
        for item in observations
    ]


__all__ = ["POLICY", "normalize_appearance", "normalize_observations"]
