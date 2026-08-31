"""Read-only G1 Fusion replay v5 with compact-appearance canonicalization after safe Window hints.

v5 keeps replay-v4's evidence-gated Window hint resolver and all accepted replay-v3 thresholds.
It changes only the comparison view used by Stages 2..4: compact Exact-Shot aliases such as
``灰卫衣``/``灰衣``/``白衣``/``白露肩装`` are canonicalized before stable-appearance fallback and
cluster/component bridges. Persisted VLM evidence and emitted source appearance text stay unchanged.

This is a read-only candidate. Production E6 is not changed until completed-run replay restores the
accepted Scene-local anonymous cast shape with zero same-Shot conflicts.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_compact_appearance_normalizer_v1 as compact_alias
from engine.app import breakdown_g1_fusion_replay_v1 as v1
from engine.app import breakdown_g1_fusion_replay_v2 as v2
from engine.app import breakdown_g1_fusion_replay_v4 as v4
from engine.app import breakdown_g1_subject_cluster_bridge_v2 as bridge_v2
from engine.app import breakdown_g1_subject_component_bridge_v3 as component_v3
from engine.app import breakdown_g1_subject_hint_resolver_v2 as hint_v2
from engine.app import breakdown_p2_fusion_episode_v4 as e4

REPLAY_PROFILE = "breakdown-g1-fusion-replay-v5"
SCENE_POLICY = v4.SCENE_POLICY
SUBJECT_POLICY = "compact-alias-normalized-after-" + v4.SUBJECT_POLICY
BASE_SUBJECT_POLICY = v4.SUBJECT_POLICY
WINDOW_HINT_RESOLUTION_POLICY = v4.WINDOW_HINT_RESOLUTION_POLICY
COMPACT_APPEARANCE_POLICY = compact_alias.POLICY
MAX_GAP_SHOTS = v4.MAX_GAP_SHOTS

_candidate_scene_plans = v4._candidate_scene_plans
format_summary = v4.format_summary


def _candidate_clusters(
    segment_plan: Any,
    window_summaries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    observations = e4._observations_for_plan(segment_plan)
    if not observations:
        return [], 0
    match_observations = compact_alias.normalize_observations(observations)

    index_by_node = {item.node_id: index for index, item in enumerate(observations)}
    uf = e4._UnionFind(observations)
    segment_ordinals = {item.shot_ordinal for item in observations}

    # Stage 1 remains replay-v4 exactly: Window ordinals are only candidate locations and Exact-Shot
    # appearance must positively support the hint. Alias-aware hint matching is handled by hint_v2.
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

    # Stages 2..4 keep accepted thresholds and hard guards, but compare canonicalized compact aliases.
    for left, right in v1._candidate_fallback_pairs(match_observations):
        if v2._explicit_observation_conflict(match_observations[left], match_observations[right]):
            continue
        uf.union(left, right)

    accepted_v2 = bridge_v2.apply_cluster_bridges(match_observations, uf)
    accepted_v3 = component_v3.apply_component_bridges(match_observations, uf)

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
            cluster["compact_appearance_policy"] = COMPACT_APPEARANCE_POLICY
            cluster["cluster_bridge_policy"] = SUBJECT_POLICY
        clusters[0]["accepted_cluster_bridge_count"] = len(accepted_v2)
        clusters[0]["accepted_component_bridge_count"] = len(accepted_v3)
        clusters[0]["base_subject_policy"] = BASE_SUBJECT_POLICY
    return clusters, conflicts


__all__ = [
    "BASE_SUBJECT_POLICY",
    "COMPACT_APPEARANCE_POLICY",
    "MAX_GAP_SHOTS",
    "REPLAY_PROFILE",
    "SCENE_POLICY",
    "SUBJECT_POLICY",
    "WINDOW_HINT_RESOLUTION_POLICY",
    "_candidate_clusters",
    "_candidate_scene_plans",
    "format_summary",
]
