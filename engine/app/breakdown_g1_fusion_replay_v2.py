"""Read-only G1 Fusion replay v2 with cluster-level anonymous-subject bridges.

Scene policy is inherited from replay v1. Subject continuity adds a second conservative stage after
Window-hint and observation-level unions: stable fragment clusters may reconnect by strong visual
consensus or by a shared same-Shot cannot-link co-star anchor. Explicit stable contradictions from
exact-Shot observations are checked before either soft union stage. Production E4 remains unchanged.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_fusion_replay_v1 as v1
from engine.app import breakdown_g1_subject_cluster_bridge_v2 as bridge
from engine.app import breakdown_p2_fusion_episode_v4 as e4

REPLAY_PROFILE = "breakdown-g1-fusion-replay-v2"
SCENE_POLICY = v1.SCENE_POLICY
SUBJECT_POLICY = bridge.POLICY
MAX_GAP_SHOTS = v1.MAX_GAP_SHOTS

_candidate_scene_plans = v1._candidate_scene_plans
format_summary = v1.format_summary


def _hair_length_classes(value: Any) -> frozenset[str]:
    styles = {
        feature.split(":", 1)[1]
        for feature in e4._stable_features(value)
        if feature.startswith("hair_style:")
    }
    result: set[str] = set()
    if styles.intersection({"长发", "披肩发"}):
        result.add("LONG")
    if styles.intersection({"短发", "寸头"}):
        result.add("SHORT")
    if "光头" in styles:
        result.add("BALD")
    return frozenset(result)


def _explicit_observation_conflict(
    left: e4.SubjectObservation,
    right: e4.SubjectObservation,
) -> bool:
    """Return True only for explicit stable contradictions strong enough to block a soft edge.

    Missing attributes never conflict. The guard is deliberately narrow: exact-Shot male/female
    disagreement and explicit long-hair versus short/bald disagreement are treated as stronger than
    Window continuity hints or appearance-similarity fallback. Dynamic action/expression/framing
    words are intentionally ignored, matching E4 identity semantics.
    """

    left_gender = e4._gender(left.appearance_summary)
    right_gender = e4._gender(right.appearance_summary)
    if left_gender and right_gender and left_gender != right_gender:
        return True

    left_hair = _hair_length_classes(left.appearance_summary)
    right_hair = _hair_length_classes(right.appearance_summary)
    if "LONG" in left_hair and right_hair.intersection({"SHORT", "BALD"}):
        return True
    if "LONG" in right_hair and left_hair.intersection({"SHORT", "BALD"}):
        return True
    return False


def _candidate_clusters(
    segment_plan: Any,
    window_summaries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    observations = e4._observations_for_plan(segment_plan)
    if not observations:
        return [], 0

    index_by_node = {item.node_id: index for index, item in enumerate(observations)}
    uf = e4._UnionFind(observations)
    segment_ordinals = {item.shot_ordinal for item in observations}

    # Stage 1: Window Context continuity is primary soft evidence, but exact-Shot explicit stable
    # contradictions are stronger and must block a soft union.
    for hint in e4._window_subject_hints(window_summaries):
        raw_ordinals = hint.get("shot_ordinals")
        if not isinstance(raw_ordinals, list):
            continue
        try:
            hint_ordinals = {int(value) for value in raw_ordinals}
        except (TypeError, ValueError):
            continue
        if not hint_ordinals.intersection(segment_ordinals):
            continue
        resolved = e4._resolve_hint_nodes(hint, observations, index_by_node)
        resolved = sorted(set(resolved), key=lambda index: observations[index].shot_ordinal)
        for left, right in zip(resolved, resolved[1:]):
            if _explicit_observation_conflict(observations[left], observations[right]):
                continue
            uf.union(left, right)

    # Stage 2: keep the accepted observation-level appearance fallback, but never let similarity
    # override an explicit stable contradiction visible in the two exact-Shot observations.
    for left, right in v1._candidate_fallback_pairs(observations):
        if _explicit_observation_conflict(observations[left], observations[right]):
            continue
        uf.union(left, right)

    # Stage 3: reconnect already-stable fragments only when cluster-level evidence is unambiguous.
    accepted_bridges = bridge.apply_cluster_bridges(observations, uf)

    grouped: dict[int, list[int]] = {}
    for index in range(len(observations)):
        grouped.setdefault(uf.find(index), []).append(index)

    ordered_groups = sorted(
        grouped.values(),
        key=lambda indexes: (
            min(observations[index].shot_ordinal for index in indexes),
            min(observations[index].label for index in indexes),
        ),
    )
    clusters: list[dict[str, Any]] = []
    conflicts = 0
    for cluster_index, indexes in enumerate(ordered_groups, start=1):
        members = sorted(
            (
                {
                    "revision_item_id": observations[index].shot_revision_item_id,
                    "shot_ordinal": observations[index].shot_ordinal,
                    "label": observations[index].label,
                    "appearance_summary": observations[index].appearance_summary,
                }
                for index in indexes
            ),
            key=lambda item: (item["shot_ordinal"], item["label"]),
        )
        shot_ids = [item["revision_item_id"] for item in members]
        duplicate_count = len(shot_ids) - len(set(shot_ids))
        conflicts += max(0, duplicate_count)
        clusters.append({
            "display_label": f"人物{chr(64 + cluster_index) if cluster_index <= 26 else cluster_index}",
            "shot_ordinals": sorted({int(item["shot_ordinal"]) for item in members}),
            "source_labels": sorted({str(item["label"]) for item in members}),
            "source_members": members,
            "same_shot_conflicts": max(0, duplicate_count),
        })

    # Replay-only provenance: useful for acceptance debugging, ignored by production schemas.
    if accepted_bridges:
        for cluster in clusters:
            cluster["cluster_bridge_policy"] = SUBJECT_POLICY
        # Keep aggregate count on the first cluster to avoid changing the compact terminal format.
        clusters[0]["accepted_cluster_bridge_count"] = len(accepted_bridges)
    return clusters, conflicts


__all__ = [
    "MAX_GAP_SHOTS",
    "REPLAY_PROFILE",
    "SCENE_POLICY",
    "SUBJECT_POLICY",
    "_candidate_clusters",
    "_candidate_scene_plans",
    "_explicit_observation_conflict",
    "format_summary",
]
