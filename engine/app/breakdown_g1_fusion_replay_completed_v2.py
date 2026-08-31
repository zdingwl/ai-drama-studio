"""Completed-run adapter for read-only G1 Fusion replay v2.

The historical Run loader stays exactly in v1. This adapter changes only the in-memory candidate
Scene/anonymous-subject policy to replay v2; it never executes providers or mutates persisted rows.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed_v1
from engine.app import breakdown_g1_fusion_replay_v2 as candidate

load_completed_fusion_inputs = completed_v1.load_completed_fusion_inputs


def replay_completed_run(run_id: str) -> dict[str, Any]:
    bundle = load_completed_fusion_inputs(run_id)
    vlm = bundle.components["VLM"].result
    metadata = vlm.metadata if isinstance(vlm.metadata, Mapping) else {}
    raw_windows = metadata.get("window_summaries")
    window_summaries = tuple(
        dict(item)
        for item in raw_windows
        if isinstance(raw_windows, list) and isinstance(item, Mapping)
    ) if isinstance(raw_windows, list) else ()

    vlm_by_shot = {
        item.shot_revision_item_id: item
        for item in vlm.evidence
        if item.source_type.strip().upper() == "VLM_OUTPUT" and item.shot_revision_item_id
    }
    details = candidate._candidate_scene_plans(bundle.context.shots, vlm_by_shot, window_summaries)

    scenes: list[dict[str, Any]] = []
    total_conflicts = 0
    for ordinal, (plan, anchor) in enumerate(details, start=1):
        clusters, conflicts = candidate._candidate_clusters(plan, window_summaries)
        total_conflicts += conflicts
        scenes.append({
            "ordinal": ordinal,
            "start_us": int(plan.shots[0].start_us),
            "end_us": int(plan.shots[-1].end_us),
            "shot_ordinals": [int(shot.ordinal) for shot in plan.shots],
            "location_hint": anchor.location,
            "interior_exterior": anchor.interior_exterior,
            "local_subject_count": len(clusters),
            "local_subjects": clusters,
            "same_shot_cluster_conflicts": conflicts,
        })

    return {
        "schema_version": candidate.REPLAY_PROFILE,
        "kind": "read_only_fusion_replay",
        "run_id": bundle.context.run_id,
        "episode_id": bundle.context.episode_id,
        "source_shot_revision_id": bundle.context.source_shot_revision_id,
        "providers_executed": [],
        "mutates_breakdown_run": False,
        "mutates_final_assets": False,
        "policies": {
            "scene": candidate.SCENE_POLICY,
            "subject_continuity": candidate.SUBJECT_POLICY,
            "max_gap_shots": candidate.MAX_GAP_SHOTS,
        },
        "source_sidecars": {
            component: {
                "fingerprint": loaded.fingerprint,
                "status": loaded.result.status,
                "provider": loaded.result.provider,
                "model": loaded.result.model,
            }
            for component, loaded in bundle.components.items()
        },
        "scene_count": len(scenes),
        "scenes": scenes,
        "same_shot_cluster_conflicts": total_conflicts,
    }


__all__ = ["load_completed_fusion_inputs", "replay_completed_run"]
