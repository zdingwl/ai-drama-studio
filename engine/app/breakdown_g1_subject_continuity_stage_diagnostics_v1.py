"""Read-only stage-by-stage diagnostics for G1 anonymous-subject continuity.

This module reads immutable completed-run sidecars only. It executes no ASR/OCR/VLM provider and
writes no Breakdown Draft/Final rows. Its purpose is to explain a continuity regression by showing
how many anonymous observation clusters remain after each currently accepted E6 subject stage:

Stage1 Window subject hints -> Stage2 stable appearance fallback -> Stage3 cluster bridge ->
Stage4 coherent component bridge.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed
from engine.app import breakdown_g1_fusion_replay_v1 as v1
from engine.app import breakdown_g1_fusion_replay_v2 as v2
from engine.app import breakdown_g1_fusion_replay_v3 as v3
from engine.app import breakdown_g1_subject_cluster_bridge_v2 as bridge_v2
from engine.app import breakdown_g1_subject_component_bridge_v3 as component_v3
from engine.app import breakdown_p2_fusion_episode_v4 as e4

DIAGNOSTIC_SCHEMA = "breakdown-g1-subject-continuity-stage-diagnostics-v1"


def _cluster_count(uf: e4._UnionFind, observation_count: int) -> int:
    return len({uf.find(index) for index in range(observation_count)})


def _resolved_rows(
    hint: Mapping[str, Any],
    observations: Sequence[e4.SubjectObservation],
    index_by_node: Mapping[tuple[str, str], int],
) -> list[dict[str, Any]]:
    indexes = e4._resolve_hint_nodes(hint, observations, index_by_node)
    rows: list[dict[str, Any]] = []
    for index in indexes:
        item = observations[index]
        rows.append({
            "shot_ordinal": item.shot_ordinal,
            "label": item.label,
            "appearance_summary": item.appearance_summary,
        })
    rows.sort(key=lambda item: (int(item["shot_ordinal"]), str(item["label"])))
    return rows


def _scene_stage_diagnostics(
    scene_ordinal: int,
    segment_plan: Any,
    window_summaries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observations = e4._observations_for_plan(segment_plan)
    index_by_node = {item.node_id: index for index, item in enumerate(observations)}
    uf = e4._UnionFind(observations)
    segment_ordinals = {item.shot_ordinal for item in observations}

    relevant_hints: list[dict[str, Any]] = []
    stage1_union_count = 0
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
        resolved = _resolved_rows(hint, observations, index_by_node)
        relevant_hints.append({
            "window_id": hint.get("window_id"),
            "appearance_summary": str(hint.get("appearance_summary") or ""),
            "shot_ordinals": sorted(hint_ordinals),
            "resolved": resolved,
            "resolved_count": len(resolved),
        })
        resolved_indexes = e4._resolve_hint_nodes(hint, observations, index_by_node)
        resolved_indexes = sorted(set(resolved_indexes), key=lambda index: observations[index].shot_ordinal)
        for left, right in zip(resolved_indexes, resolved_indexes[1:]):
            if v2._explicit_observation_conflict(observations[left], observations[right]):
                continue
            if uf.union(left, right):
                stage1_union_count += 1

    after_stage1 = _cluster_count(uf, len(observations))

    stage2_pairs = v1._candidate_fallback_pairs(observations)
    stage2_union_count = 0
    for left, right in stage2_pairs:
        if v2._explicit_observation_conflict(observations[left], observations[right]):
            continue
        if uf.union(left, right):
            stage2_union_count += 1
    after_stage2 = _cluster_count(uf, len(observations))

    accepted_stage3 = bridge_v2.apply_cluster_bridges(observations, uf)
    after_stage3 = _cluster_count(uf, len(observations))

    accepted_stage4 = component_v3.apply_component_bridges(observations, uf)
    after_stage4 = _cluster_count(uf, len(observations))

    final_clusters, conflicts = v3._candidate_clusters(segment_plan, window_summaries)
    return {
        "scene_ordinal": scene_ordinal,
        "shot_ordinals": [int(shot.ordinal) for shot in segment_plan.shots],
        "observation_count": len(observations),
        "observations": [
            {
                "shot_ordinal": item.shot_ordinal,
                "label": item.label,
                "appearance_summary": item.appearance_summary,
                "stable_features": sorted(e4._stable_features(item.appearance_summary)),
            }
            for item in observations
        ],
        "window_hint_count": len(relevant_hints),
        "window_hints_resolving_2plus": sum(1 for item in relevant_hints if int(item["resolved_count"]) >= 2),
        "window_hints": relevant_hints,
        "stage1": {
            "name": "window_hints",
            "accepted_union_count": stage1_union_count,
            "cluster_count": after_stage1,
        },
        "stage2": {
            "name": "stable_appearance_fallback",
            "candidate_pair_count": len(stage2_pairs),
            "accepted_union_count": stage2_union_count,
            "cluster_count": after_stage2,
        },
        "stage3": {
            "name": "mutual_best_cluster_bridge",
            "accepted_union_count": len(accepted_stage3),
            "cluster_count": after_stage3,
        },
        "stage4": {
            "name": "coherent_component_bridge",
            "accepted_union_count": len(accepted_stage4),
            "cluster_count": after_stage4,
        },
        "final_cluster_count": len(final_clusters),
        "same_shot_cluster_conflicts": int(conflicts),
        "final_clusters": final_clusters,
    }


def inspect_run(run_id: str) -> dict[str, Any]:
    bundle = completed.load_completed_fusion_inputs(run_id)
    vlm = bundle.components["VLM"].result
    metadata = vlm.metadata if isinstance(vlm.metadata, Mapping) else {}
    raw_windows = metadata.get("window_summaries")
    window_summaries = tuple(
        dict(item) for item in raw_windows
        if isinstance(raw_windows, list) and isinstance(item, Mapping)
    ) if isinstance(raw_windows, list) else ()
    vlm_by_shot = {
        item.shot_revision_item_id: item
        for item in vlm.evidence
        if item.source_type.strip().upper() == "VLM_OUTPUT" and item.shot_revision_item_id
    }
    details = v3._candidate_scene_plans(bundle.context.shots, vlm_by_shot, window_summaries)
    scenes = [
        _scene_stage_diagnostics(index, plan, window_summaries)
        for index, (plan, _anchor) in enumerate(details, start=1)
    ]
    return {
        "schema_version": DIAGNOSTIC_SCHEMA,
        "run_id": run_id,
        "episode_id": bundle.context.episode_id,
        "providers_executed": [],
        "mutates_breakdown_run": False,
        "mutates_final_assets": False,
        "scene_count": len(scenes),
        "scenes": scenes,
    }


def format_summary(payload: Mapping[str, Any], *, show_hints: int = 8) -> str:
    lines = [
        "=== G1 人物连续性 Stage 诊断（只读）===",
        f"Run: {payload.get('run_id')}",
        "providers_executed=[] | mutates_breakdown_run=false | mutates_final_assets=false",
    ]
    for scene in payload.get("scenes", []):
        if not isinstance(scene, Mapping):
            continue
        shots = list(scene.get("shot_ordinals") or [])
        shot_text = f"{shots[0]}-{shots[-1]}" if shots else "-"
        lines.append(
            f"\n[Scene {scene.get('scene_ordinal')}] shots={shot_text} | observations={scene.get('observation_count')} "
            f"| final_clusters={scene.get('final_cluster_count')} | conflicts={scene.get('same_shot_cluster_conflicts')}"
        )
        lines.append(
            "  hints={hints} | resolving>=2={resolved}".format(
                hints=scene.get("window_hint_count"),
                resolved=scene.get("window_hints_resolving_2plus"),
            )
        )
        for key in ("stage1", "stage2", "stage3", "stage4"):
            stage = scene.get(key)
            if not isinstance(stage, Mapping):
                continue
            extra = ""
            if stage.get("candidate_pair_count") is not None:
                extra = f" candidates={stage.get('candidate_pair_count')}"
            lines.append(
                f"  {key}: clusters={stage.get('cluster_count')} | unions={stage.get('accepted_union_count')}{extra}"
            )
        hints = [item for item in scene.get("window_hints", []) if isinstance(item, Mapping)]
        for hint in hints[:max(0, int(show_hints))]:
            resolved = ", ".join(
                f"{item.get('shot_ordinal')}:{item.get('label')}[{item.get('appearance_summary')}]"
                for item in hint.get("resolved", []) if isinstance(item, Mapping)
            ) or "-"
            lines.append(
                f"    hint {hint.get('window_id') or '-'} | {hint.get('appearance_summary') or '-'} "
                f"| shots={','.join(str(v) for v in hint.get('shot_ordinals', []))} | resolved={resolved}"
            )
        lines.append("  final:")
        for cluster in scene.get("final_clusters", []):
            if not isinstance(cluster, Mapping):
                continue
            lines.append(
                "    {label}: shots={shots}".format(
                    label=cluster.get("display_label"),
                    shots=",".join(str(v) for v in cluster.get("shot_ordinals", [])),
                )
            )
            members = [item for item in cluster.get("source_members", []) if isinstance(item, Mapping)]
            examples = "; ".join(
                f"{item.get('shot_ordinal')}:{item.get('appearance_summary')}" for item in members[:3]
            )
            if examples:
                lines.append(f"      {examples}")
    return "\n".join(lines)


__all__ = ["DIAGNOSTIC_SCHEMA", "format_summary", "inspect_run"]
