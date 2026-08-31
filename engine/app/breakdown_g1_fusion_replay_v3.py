"""Read-only G1 Fusion replay v3 for Scene01 coherent anonymous-subject continuity.

v3 keeps the accepted v2 Scene policy, exact-Shot conflict guard, observation fallback and cluster
bridge. It adds one final read-only coherent-component phase to recover obvious same-person chains
that v2's mutual-best tie rule intentionally froze. Production E5 is NOT changed by this module.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_fusion_replay_v1 as v1
from engine.app import breakdown_g1_fusion_replay_v2 as v2
from engine.app import breakdown_g1_subject_cluster_bridge_v2 as bridge_v2
from engine.app import breakdown_g1_subject_component_bridge_v3 as component_v3
from engine.app import breakdown_p2_fusion_episode_v4 as e4

REPLAY_PROFILE = "breakdown-g1-fusion-replay-v3"
SCENE_POLICY = v2.SCENE_POLICY
SUBJECT_POLICY = component_v3.POLICY
BASE_SUBJECT_POLICY = v2.SUBJECT_POLICY
MAX_GAP_SHOTS = v2.MAX_GAP_SHOTS

_candidate_scene_plans = v2._candidate_scene_plans
format_summary = v2.format_summary


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

    # Stage 1: same v2 Window soft edges with exact-Shot explicit conflict guard.
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
            if v2._explicit_observation_conflict(observations[left], observations[right]):
                continue
            uf.union(left, right)

    # Stage 2: same v2 conservative observation fallback with conflict guard.
    for left, right in v1._candidate_fallback_pairs(observations):
        if v2._explicit_observation_conflict(observations[left], observations[right]):
            continue
        uf.union(left, right)

    # Stage 3: accepted v2 mutual-best cluster bridge.
    accepted_v2 = bridge_v2.apply_cluster_bridges(observations, uf)

    # Stage 4: v3 read-only coherent component bridge. This is the only new candidate behavior.
    accepted_v3 = component_v3.apply_component_bridges(observations, uf)

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

    if clusters and (accepted_v2 or accepted_v3):
        for cluster in clusters:
            cluster["cluster_bridge_policy"] = SUBJECT_POLICY
        clusters[0]["accepted_cluster_bridge_count"] = len(accepted_v2)
        clusters[0]["accepted_component_bridge_count"] = len(accepted_v3)
        clusters[0]["base_subject_policy"] = BASE_SUBJECT_POLICY
    return clusters, conflicts


__all__ = [
    "BASE_SUBJECT_POLICY",
    "MAX_GAP_SHOTS",
    "REPLAY_PROFILE",
    "SCENE_POLICY",
    "SUBJECT_POLICY",
    "_candidate_clusters",
    "_candidate_scene_plans",
    "format_summary",
]
