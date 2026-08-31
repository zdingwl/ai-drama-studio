"""Cluster-level bridge policy for read-only G1 anonymous subject replay.

This module is deliberately NOT wired into production E4 Fusion. It only strengthens the read-only
candidate replay after the existing Window-hint + conservative observation-level unions have formed
short anonymous fragments. Every merge still passes through E4's UnionFind, so the transitive
same-Shot hard cannot-link remains authoritative.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Sequence

from engine.app import breakdown_p2_fusion_episode_v4 as e4

POLICY = "cluster-visual-plus-common-costar-mutual-best-hard-same-shot-v2"
MAX_CLUSTER_GAP_SHOTS = 3
MIN_BEST_MARGIN = 0.5

_IDENTITY_PREFIXES = frozenset({"hair_style", "hair_color", "color", "clothing", "accessory"})


@dataclass(frozen=True)
class ClusterProfile:
    root: int
    member_indexes: tuple[int, ...]
    shot_ids: frozenset[str]
    shot_ordinals: frozenset[int]
    genders: frozenset[str]
    consensus_features: frozenset[str]
    identity_features: frozenset[str]


@dataclass(frozen=True)
class BridgeCandidate:
    left_root: int
    right_root: int
    score: float
    gap_shots: int
    shared_identity_count: int
    common_cannot_link_count: int
    max_similarity: float
    top3_mean: float
    support_4_strong2: int
    support_3_strong2: int
    reason: str


def _feature_prefix(feature: str) -> str:
    return feature.split(":", 1)[0]


def _cluster_gap(left: ClusterProfile, right: ClusterProfile) -> int:
    a = sorted(left.shot_ordinals)
    b = sorted(right.shot_ordinals)
    if not a or not b:
        return 10**9
    if a[-1] < b[0]:
        return b[0] - a[-1]
    if b[-1] < a[0]:
        return a[0] - b[-1]
    return 0


def _profile(
    observations: Sequence[e4.SubjectObservation],
    *,
    root: int,
    indexes: Sequence[int],
) -> ClusterProfile:
    feature_counts: Counter[str] = Counter()
    genders: set[str] = set()
    shot_ids: set[str] = set()
    ordinals: set[int] = set()
    for index in indexes:
        item = observations[index]
        shot_ids.add(item.shot_revision_item_id)
        ordinals.add(item.shot_ordinal)
        gender = e4._gender(item.appearance_summary)
        if gender:
            genders.add(gender)
        for feature in e4._stable_features(item.appearance_summary):
            feature_counts[feature] += 1

    observation_count = max(1, len(indexes))
    consensus_min = 1 if observation_count <= 2 else max(2, math.ceil(observation_count * 0.35))
    consensus = {
        feature
        for feature, count in feature_counts.items()
        if count >= consensus_min
    }
    identity = {
        feature
        for feature in consensus
        if _feature_prefix(feature) in _IDENTITY_PREFIXES
    }
    return ClusterProfile(
        root=root,
        member_indexes=tuple(sorted(indexes)),
        shot_ids=frozenset(shot_ids),
        shot_ordinals=frozenset(ordinals),
        genders=frozenset(genders),
        consensus_features=frozenset(consensus),
        identity_features=frozenset(identity),
    )


def _profiles(
    observations: Sequence[e4.SubjectObservation],
    uf: e4._UnionFind,
) -> dict[int, ClusterProfile]:
    grouped: dict[int, list[int]] = {}
    for index in range(len(observations)):
        grouped.setdefault(uf.find(index), []).append(index)
    return {
        root: _profile(observations, root=root, indexes=indexes)
        for root, indexes in grouped.items()
    }


def _consensus_values(profile: ClusterProfile, prefix: str) -> set[str]:
    marker = f"{prefix}:"
    return {
        feature[len(marker):]
        for feature in profile.consensus_features
        if feature.startswith(marker)
    }


def _hard_profile_conflict(left: ClusterProfile, right: ClusterProfile) -> bool:
    if left.genders and right.genders and left.genders.isdisjoint(right.genders):
        return True

    # Long-vs-short hair is a strong identity contradiction in this anonymous Draft layer.
    # Missing hair style is not a contradiction; only explicit incompatible stable consensus is.
    left_hair = _consensus_values(left, "hair_style")
    right_hair = _consensus_values(right, "hair_style")
    if left_hair and right_hair and left_hair.isdisjoint(right_hair):
        return True
    return False


def _pairwise_similarity(
    observations: Sequence[e4.SubjectObservation],
    left: ClusterProfile,
    right: ClusterProfile,
) -> tuple[float, float, int, int]:
    rows: list[tuple[float, int]] = []
    for left_index in left.member_indexes:
        for right_index in right.member_indexes:
            score, strong = e4._appearance_similarity(
                observations[left_index].appearance_summary,
                observations[right_index].appearance_summary,
            )
            if math.isfinite(score):
                rows.append((float(score), int(strong)))
    rows.sort(reverse=True)
    if not rows:
        return -math.inf, -math.inf, 0, 0
    top = rows[:3]
    max_score = top[0][0]
    top3_mean = sum(score for score, _strong in top) / len(top)
    support_4 = sum(1 for score, strong in rows if score >= 4.0 and strong >= 2)
    support_3 = sum(1 for score, strong in rows if score >= 3.0 and strong >= 2)
    return max_score, top3_mean, support_4, support_3


def _common_cannot_link_count(
    left: ClusterProfile,
    right: ClusterProfile,
    profiles: dict[int, ClusterProfile],
) -> int:
    count = 0
    for root, other in profiles.items():
        if root in {left.root, right.root}:
            continue
        if left.shot_ids.intersection(other.shot_ids) and right.shot_ids.intersection(other.shot_ids):
            count += 1
    return count


def _candidate(
    observations: Sequence[e4.SubjectObservation],
    left: ClusterProfile,
    right: ClusterProfile,
    profiles: dict[int, ClusterProfile],
) -> BridgeCandidate | None:
    if left.shot_ids.intersection(right.shot_ids):
        return None
    gap = _cluster_gap(left, right)
    if gap > MAX_CLUSTER_GAP_SHOTS:
        return None
    if _hard_profile_conflict(left, right):
        return None

    shared_identity = left.identity_features.intersection(right.identity_features)
    shared_identity_count = len(shared_identity)
    max_similarity, top3_mean, support_4, support_3 = _pairwise_similarity(
        observations, left, right
    )
    if not math.isfinite(max_similarity):
        return None
    common_cannot_link = _common_cannot_link_count(left, right, profiles)

    strong_visual = (
        shared_identity_count >= 3
        and top3_mean >= 3.0
        and support_3 >= 1
    )
    common_costar = (
        common_cannot_link >= 1
        and shared_identity_count >= 2
        and max_similarity >= 3.5
        and support_3 >= 1
    )
    if not strong_visual and not common_costar:
        return None

    gap_bonus = 1.0 if gap <= 1 else 0.5 if gap <= 3 else 0.0
    score = (
        top3_mean
        + 0.70 * min(shared_identity_count, 4)
        + 1.50 * min(common_cannot_link, 2)
        + 0.50 * min(support_4, 4)
        + gap_bonus
    )
    return BridgeCandidate(
        left_root=left.root,
        right_root=right.root,
        score=score,
        gap_shots=gap,
        shared_identity_count=shared_identity_count,
        common_cannot_link_count=common_cannot_link,
        max_similarity=max_similarity,
        top3_mean=top3_mean,
        support_4_strong2=support_4,
        support_3_strong2=support_3,
        reason="strong_visual" if strong_visual else "common_costar",
    )


def _best_mutual_pairs(candidates: Sequence[BridgeCandidate]) -> list[BridgeCandidate]:
    by_root: dict[int, list[BridgeCandidate]] = {}
    for item in candidates:
        by_root.setdefault(item.left_root, []).append(item)
        by_root.setdefault(item.right_root, []).append(item)

    best: dict[int, BridgeCandidate] = {}
    for root, rows in by_root.items():
        ranked = sorted(
            rows,
            key=lambda item: (
                item.score,
                item.support_4_strong2,
                item.shared_identity_count,
                -item.gap_shots,
                -min(item.left_root, item.right_root),
            ),
            reverse=True,
        )
        if not ranked:
            continue
        if len(ranked) > 1 and ranked[0].score - ranked[1].score < MIN_BEST_MARGIN:
            continue
        best[root] = ranked[0]

    result: list[BridgeCandidate] = []
    seen: set[tuple[int, int]] = set()
    for root, item in best.items():
        other = item.right_root if item.left_root == root else item.left_root
        if best.get(other) is not item:
            continue
        pair = tuple(sorted((root, other)))
        if pair in seen:
            continue
        seen.add(pair)
        result.append(item)
    result.sort(key=lambda item: item.score, reverse=True)
    return result


def apply_cluster_bridges(
    observations: Sequence[e4.SubjectObservation],
    uf: e4._UnionFind,
) -> list[BridgeCandidate]:
    """Iteratively merge unambiguous fragment clusters while preserving E4 hard cannot-link."""

    accepted: list[BridgeCandidate] = []
    for _round in range(max(1, len(observations))):
        profiles = _profiles(observations, uf)
        roots = sorted(profiles)
        candidates: list[BridgeCandidate] = []
        for left_pos, left_root in enumerate(roots):
            for right_root in roots[left_pos + 1:]:
                item = _candidate(
                    observations,
                    profiles[left_root],
                    profiles[right_root],
                    profiles,
                )
                if item is not None:
                    candidates.append(item)
        mutual = _best_mutual_pairs(candidates)
        if not mutual:
            break

        merged_any = False
        for item in mutual:
            left_root = uf.find(item.left_root)
            right_root = uf.find(item.right_root)
            if left_root == right_root:
                continue
            if uf.union(left_root, right_root):
                accepted.append(item)
                merged_any = True
        if not merged_any:
            break
    return accepted


__all__ = [
    "BridgeCandidate",
    "MAX_CLUSTER_GAP_SHOTS",
    "MIN_BEST_MARGIN",
    "POLICY",
    "apply_cluster_bridges",
]
