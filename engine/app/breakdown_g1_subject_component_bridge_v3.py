"""Read-only G1 v3 coherent-component bridge for anonymous subject fragments.

v2 deliberately used mutual-best matching, which is safe but can freeze a whole obvious chain when
several adjacent fragments have the same score. v3 stays read-only and adds a later, stricter phase:

- only operate on clusters that survived v2;
- require temporal proximity and no same-Shot overlap;
- keep explicit gender / long-vs-short hair contradictions as hard blockers;
- recover a few highly stable attire details that v2's coarse feature vocabulary drops;
- seed only with a shared co-star cannot-link anchor or a shared distinctive attire detail;
- merge a connected component only if the whole component is globally same-Shot safe;
- after a safe multi-fragment component exists, allow a tiny singleton/two-observation fragment to
  grow into it by strong base appearance evidence.

This remains anonymous Scene-local continuity, never Character identity.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Sequence

from engine.app import breakdown_g1_fusion_replay_v2 as v2
from engine.app import breakdown_p2_fusion_episode_v4 as e4

POLICY = "coherent-component-distinctive-attire-hard-same-shot-v3"
MAX_COMPONENT_GAP_SHOTS = 3

_EXTRA_COLOR_TOKENS = (
    "橙色", "橘色", "银色", "金色", "卡其色", "藏青色", "藏青", "咖色",
)
_ATTIRE_DETAIL_TOKENS = (
    "露肩", "连帽衫", "花卉", "印花", "格纹", "条纹", "波点", "蕾丝", "牛仔",
    "皮革", "针织", "高腰", "阔腿", "无袖", "长袖", "短袖",
)
_IDENTITY_PREFIXES = frozenset({"hair_style", "hair_color", "color", "clothing", "accessory", "attire_detail"})


@dataclass(frozen=True)
class ClusterProfile:
    root: int
    member_indexes: tuple[int, ...]
    shot_ids: frozenset[str]
    shot_ordinals: frozenset[int]
    genders: frozenset[str]
    hair_classes: frozenset[str]
    identity_features: frozenset[str]
    distinctive_features: frozenset[str]

    @property
    def member_count(self) -> int:
        return len(self.member_indexes)


@dataclass(frozen=True)
class ComponentEdge:
    left_root: int
    right_root: int
    score: float
    gap_shots: int
    shared_identity_count: int
    shared_distinctive_count: int
    common_cannot_link_count: int
    max_similarity: float
    top3_mean: float
    reason: str


def _extra_features(value: str) -> set[str]:
    text = str(value or "")
    result: set[str] = set()
    for token in _EXTRA_COLOR_TOKENS:
        if token in text:
            result.add(f"color:{token}")
    for token in _ATTIRE_DETAIL_TOKENS:
        if token in text:
            result.add(f"attire_detail:{token}")
    return result


def _all_identity_features(value: str) -> set[str]:
    features = {
        item for item in e4._stable_features(value)
        if item.split(":", 1)[0] in _IDENTITY_PREFIXES
    }
    features.update(_extra_features(value))
    return features


def _profile(
    observations: Sequence[e4.SubjectObservation],
    *,
    root: int,
    indexes: Sequence[int],
) -> ClusterProfile:
    feature_counts: Counter[str] = Counter()
    distinctive_counts: Counter[str] = Counter()
    shot_ids: set[str] = set()
    ordinals: set[int] = set()
    genders: set[str] = set()
    hair_classes: set[str] = set()

    for index in indexes:
        item = observations[index]
        shot_ids.add(item.shot_revision_item_id)
        ordinals.add(item.shot_ordinal)
        gender = e4._gender(item.appearance_summary)
        if gender:
            genders.add(gender)
        hair_classes.update(v2._hair_length_classes(item.appearance_summary))
        for feature in _all_identity_features(item.appearance_summary):
            feature_counts[feature] += 1
            if feature.startswith("attire_detail:") or feature.split(":", 1)[1] in _EXTRA_COLOR_TOKENS:
                distinctive_counts[feature] += 1

    count = max(1, len(indexes))
    consensus_min = 1 if count <= 2 else max(2, math.ceil(count * 0.35))
    distinctive_min = 1 if count <= 3 else 2
    identity = {feature for feature, seen in feature_counts.items() if seen >= consensus_min}
    distinctive = {feature for feature, seen in distinctive_counts.items() if seen >= distinctive_min}
    identity.update(distinctive)

    return ClusterProfile(
        root=root,
        member_indexes=tuple(sorted(indexes)),
        shot_ids=frozenset(shot_ids),
        shot_ordinals=frozenset(ordinals),
        genders=frozenset(genders),
        hair_classes=frozenset(hair_classes),
        identity_features=frozenset(identity),
        distinctive_features=frozenset(distinctive),
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


def _gap(left: ClusterProfile, right: ClusterProfile) -> int:
    a = sorted(left.shot_ordinals)
    b = sorted(right.shot_ordinals)
    if not a or not b:
        return 10**9
    if a[-1] < b[0]:
        return b[0] - a[-1]
    if b[-1] < a[0]:
        return a[0] - b[-1]
    return 0


def _hard_conflict(left: ClusterProfile, right: ClusterProfile) -> bool:
    if left.genders and right.genders and left.genders.isdisjoint(right.genders):
        return True
    if "LONG" in left.hair_classes and right.hair_classes.intersection({"SHORT", "BALD"}):
        return True
    if "LONG" in right.hair_classes and left.hair_classes.intersection({"SHORT", "BALD"}):
        return True
    return False


def _pairwise_similarity(
    observations: Sequence[e4.SubjectObservation],
    left: ClusterProfile,
    right: ClusterProfile,
) -> tuple[float, float]:
    scores: list[float] = []
    for left_index in left.member_indexes:
        for right_index in right.member_indexes:
            score, _strong = e4._appearance_similarity(
                observations[left_index].appearance_summary,
                observations[right_index].appearance_summary,
            )
            if math.isfinite(score):
                scores.append(float(score))
    scores.sort(reverse=True)
    if not scores:
        return -math.inf, -math.inf
    top = scores[:3]
    return scores[0], sum(top) / len(top)


def _common_cannot_link_count(
    left: ClusterProfile,
    right: ClusterProfile,
    profiles: dict[int, ClusterProfile],
) -> int:
    return sum(
        1
        for root, other in profiles.items()
        if root not in {left.root, right.root}
        and left.shot_ids.intersection(other.shot_ids)
        and right.shot_ids.intersection(other.shot_ids)
    )


def _seed_edge(
    observations: Sequence[e4.SubjectObservation],
    left: ClusterProfile,
    right: ClusterProfile,
    profiles: dict[int, ClusterProfile],
) -> ComponentEdge | None:
    if left.shot_ids.intersection(right.shot_ids):
        return None
    gap = _gap(left, right)
    if gap > MAX_COMPONENT_GAP_SHOTS or _hard_conflict(left, right):
        return None

    shared = left.identity_features.intersection(right.identity_features)
    shared_distinctive = left.distinctive_features.intersection(right.distinctive_features)
    if len(shared) < 3:
        return None
    max_similarity, top3_mean = _pairwise_similarity(observations, left, right)
    if not math.isfinite(max_similarity):
        return None
    common = _common_cannot_link_count(left, right, profiles)

    by_costar = common >= 1 and max_similarity >= 3.0
    by_distinctive = bool(shared_distinctive) and max_similarity >= 2.5
    if not by_costar and not by_distinctive:
        return None

    gap_bonus = 1.0 if gap <= 1 else 0.5
    score = (
        max_similarity
        + 0.5 * min(len(shared), 5)
        + 1.25 * min(common, 2)
        + 1.0 * min(len(shared_distinctive), 2)
        + gap_bonus
    )
    return ComponentEdge(
        left_root=left.root,
        right_root=right.root,
        score=score,
        gap_shots=gap,
        shared_identity_count=len(shared),
        shared_distinctive_count=len(shared_distinctive),
        common_cannot_link_count=common,
        max_similarity=max_similarity,
        top3_mean=top3_mean,
        reason="common_costar" if by_costar else "distinctive_attire",
    )


def _connected_components(edges: Sequence[ComponentEdge]) -> list[tuple[set[int], list[ComponentEdge]]]:
    adjacency: dict[int, set[int]] = {}
    for edge in edges:
        adjacency.setdefault(edge.left_root, set()).add(edge.right_root)
        adjacency.setdefault(edge.right_root, set()).add(edge.left_root)

    result: list[tuple[set[int], list[ComponentEdge]]] = []
    seen: set[int] = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        nodes: set[int] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            nodes.add(node)
            stack.extend(sorted(adjacency.get(node, ()), reverse=True))
        component_edges = [edge for edge in edges if edge.left_root in nodes and edge.right_root in nodes]
        result.append((nodes, component_edges))
    return result


def _component_safe(nodes: set[int], profiles: dict[int, ClusterProfile]) -> bool:
    ordered = sorted(nodes)
    seen_shots: set[str] = set()
    for root in ordered:
        shots = profiles[root].shot_ids
        if seen_shots.intersection(shots):
            return False
        seen_shots.update(shots)
    for left_pos, left_root in enumerate(ordered):
        for right_root in ordered[left_pos + 1:]:
            if _hard_conflict(profiles[left_root], profiles[right_root]):
                return False
    return True


def _merge_component(
    uf: e4._UnionFind,
    nodes: set[int],
    edges: Sequence[ComponentEdge],
) -> list[ComponentEdge]:
    if len(nodes) < 2:
        return []
    accepted: list[ComponentEdge] = []
    merged_nodes = {min(nodes)}
    remaining = sorted(edges, key=lambda item: item.score, reverse=True)
    while len(merged_nodes) < len(nodes):
        progress = False
        for edge in remaining:
            left_in = edge.left_root in merged_nodes
            right_in = edge.right_root in merged_nodes
            if left_in == right_in:
                continue
            if uf.union(uf.find(edge.left_root), uf.find(edge.right_root)):
                accepted.append(edge)
            merged_nodes.add(edge.left_root)
            merged_nodes.add(edge.right_root)
            progress = True
            break
        if not progress:
            break
    return accepted


def _growth_candidate(
    observations: Sequence[e4.SubjectObservation],
    left: ClusterProfile,
    right: ClusterProfile,
) -> ComponentEdge | None:
    if left.shot_ids.intersection(right.shot_ids):
        return None
    if min(left.member_count, right.member_count) > 2:
        return None
    if max(left.member_count, right.member_count) < 2:
        return None
    gap = _gap(left, right)
    if gap > MAX_COMPONENT_GAP_SHOTS or _hard_conflict(left, right):
        return None
    shared = left.identity_features.intersection(right.identity_features)
    if len(shared) < 3:
        return None
    max_similarity, top3_mean = _pairwise_similarity(observations, left, right)
    if not math.isfinite(max_similarity) or max_similarity < 3.0:
        return None
    score = max_similarity + 0.5 * min(len(shared), 5) + (1.0 if gap <= 1 else 0.5)
    return ComponentEdge(
        left_root=left.root,
        right_root=right.root,
        score=score,
        gap_shots=gap,
        shared_identity_count=len(shared),
        shared_distinctive_count=len(left.distinctive_features.intersection(right.distinctive_features)),
        common_cannot_link_count=0,
        max_similarity=max_similarity,
        top3_mean=top3_mean,
        reason="small_fragment_growth",
    )


def apply_component_bridges(
    observations: Sequence[e4.SubjectObservation],
    uf: e4._UnionFind,
) -> list[ComponentEdge]:
    """Merge only globally safe coherent components, then attach tiny strong-matching fragments."""

    accepted: list[ComponentEdge] = []

    # Phase A: connected components seeded by structural co-star evidence or distinctive attire.
    profiles = _profiles(observations, uf)
    roots = sorted(profiles)
    seed_edges: list[ComponentEdge] = []
    for left_pos, left_root in enumerate(roots):
        for right_root in roots[left_pos + 1:]:
            edge = _seed_edge(observations, profiles[left_root], profiles[right_root], profiles)
            if edge is not None:
                seed_edges.append(edge)
    for nodes, edges in _connected_components(seed_edges):
        if _component_safe(nodes, profiles):
            accepted.extend(_merge_component(uf, nodes, edges))

    # Phase B: after a safe component exists, let only tiny fragments grow into it by strong base evidence.
    for _round in range(max(1, len(observations))):
        profiles = _profiles(observations, uf)
        roots = sorted(profiles)
        candidates: list[ComponentEdge] = []
        for left_pos, left_root in enumerate(roots):
            for right_root in roots[left_pos + 1:]:
                edge = _growth_candidate(observations, profiles[left_root], profiles[right_root])
                if edge is not None:
                    candidates.append(edge)
        if not candidates:
            break

        # Keep growth conservative: accept only a mutual unique best edge per round.
        by_root: dict[int, list[ComponentEdge]] = {}
        for edge in candidates:
            by_root.setdefault(edge.left_root, []).append(edge)
            by_root.setdefault(edge.right_root, []).append(edge)
        best: dict[int, ComponentEdge] = {}
        for root, rows in by_root.items():
            ranked = sorted(rows, key=lambda item: item.score, reverse=True)
            if len(ranked) > 1 and ranked[0].score - ranked[1].score < 0.5:
                continue
            best[root] = ranked[0]

        chosen: ComponentEdge | None = None
        for root, edge in sorted(best.items()):
            other = edge.right_root if edge.left_root == root else edge.left_root
            if best.get(other) is edge:
                chosen = edge
                break
        if chosen is None:
            break
        if uf.union(uf.find(chosen.left_root), uf.find(chosen.right_root)):
            accepted.append(chosen)
        else:
            break

    return accepted


__all__ = [
    "ComponentEdge",
    "MAX_COMPONENT_GAP_SHOTS",
    "POLICY",
    "apply_component_bridges",
]
