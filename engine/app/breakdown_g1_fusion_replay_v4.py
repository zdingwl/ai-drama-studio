"""Read-only G1 Fusion replay v4 with evidence-gated Window subject-hint resolution.

v4 keeps the accepted replay-v3 Scene policy and Stages 2..4 unchanged. It changes Stage1 only:
ordinal-only Window subject hints no longer auto-bind the sole visible person in a Shot. The hinted
appearance must have positive stable support in the Exact-Shot observation. This addresses the real
compact-v3 regression where white-clothed-woman hints absorbed gray-hoodie men (and vice versa).

This module is read-only candidate logic. Production E6 is not changed until completed-run replay
restores the accepted two-person Scene shape with zero same-Shot conflicts.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_fusion_replay_v1 as v1
from engine.app import breakdown_g1_fusion_replay_v2 as v2
from engine.app import breakdown_g1_fusion_replay_v3 as v3
from engine.app import breakdown_g1_subject_cluster_bridge_v2 as bridge_v2
from engine.app import breakdown_g1_subject_component_bridge_v3 as component_v3
from engine.app import breakdown_g1_subject_hint_resolver_v2 as hint_v2
from engine.app import breakdown_p2_fusion_episode_v4 as e4

REPLAY_PROFILE = "breakdown-g1-fusion-replay-v4"
SCENE_POLICY = v3.SCENE_POLICY
SUBJECT_POLICY = "evidence-gated-window-hint-plus-" + component_v3.POLICY
BASE_SUBJECT_POLICY = v3.SUBJECT_POLICY
WINDOW_HINT_RESOLUTION_POLICY = hint_v2.POLICY
MAX_GAP_SHOTS = v3.MAX_GAP_SHOTS

_candidate_scene_plans = v3._candidate_scene_plans
format_summary = v3.format_summary


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

    # Stage 1: Window hints stay soft, but a listed ordinal only marks a candidate Shot. Exact-Shot
    # appearance must positively support the hinted anonymous person before an edge is created.
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
        resolved = hint_v2.resolve_hint_nodes(hint, observations, index_by_node)
        resolved = sorted(set(resolved), key=lambda index: observations[index].shot_ordinal)
        for left, right in zip(resolved, resolved[1:]):
            if v2._explicit_observation_conflict(observations[left], observations[right]):
                continue
            uf.union(left, right)

    # Stage 2: accepted observation-level appearance fallback + explicit conflict guard.
    for left, right in v1._candidate_fallback_pairs(observations):
        if v2._explicit_observation_conflict(observations[left], observations[right]):
            continue
        uf.union(left, right)

    # Stage 3: accepted mutual-best cluster bridge.
    accepted_v2 = bridge_v2.apply_cluster_bridges(observations, uf)

    # Stage 4: accepted coherent-component bridge.
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

    if clusters:
        for cluster in clusters:
            cluster["window_hint_resolution_policy"] = WINDOW_HINT_RESOLUTION_POLICY
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
    "WINDOW_HINT_RESOLUTION_POLICY",
    "_candidate_clusters",
    "_candidate_scene_plans",
    "format_summary",
]
