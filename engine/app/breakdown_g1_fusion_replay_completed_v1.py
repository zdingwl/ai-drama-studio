"""Completed-run adapter for read-only G1 Fusion replay.

This module is intentionally separate from production P2 loaders. Production providers/Fusion
remain PROCESSING-only. Replay may read only completed READY-like historical Runs, reconstruct the
frozen ShotRevision context, verify the already-persisted immutable sidecars, and evaluate candidate
Scene/anonymous-subject continuity entirely in memory.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import select

from engine.app import breakdown_g1_fusion_replay_v1 as candidate
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem

_ALLOWED_RUN_STATUSES = frozenset({"READY", "READY_WITH_WARNINGS", "STALE"})
_REQUIRED_COMPONENTS = ("ASR", "OCR", "VLM")
_ALLOWED_DEGRADED_STATUSES = frozenset({"NO_EVIDENCE", "NOT_AVAILABLE"})


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _keyframes(raw: str | None) -> tuple[Any, ...]:
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    return tuple(value) if isinstance(value, list) else ()


def load_completed_fusion_inputs(run_id: str) -> legacy.FusionInputBundle:
    """Load/verify immutable P2 sidecars for a completed historical Run without provider execution."""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        if run.status not in _ALLOWED_RUN_STATUSES:
            raise legacy.BreakdownP2FusionError(
                "G1 只读重放仅允许 READY / READY_WITH_WARNINGS / STALE Run；"
                f"当前状态为 {run.status}"
            )

        project = session.get(studio_v2.Project, run.project_id)
        episode = session.get(studio_v2.Episode, run.episode_id)
        revision = session.get(ShotRevision, run.source_shot_revision_id)
        if project is None or episode is None or revision is None:
            raise legacy.BreakdownP2FusionError("Breakdown Run 的 Project/Episode/ShotRevision 历史锚点不完整")
        if episode.project_id != run.project_id or revision.episode_id != run.episode_id:
            raise legacy.BreakdownP2FusionError("Breakdown Run 的历史 Project/Episode/ShotRevision 锚点不一致")

        items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == revision.id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        if not items:
            raise legacy.BreakdownP2FusionError("Run source ShotRevision 没有 ShotRevisionItem")

        preprocess = session.scalar(
            select(studio_v2.Preprocess).where(studio_v2.Preprocess.episode_id == episode.id)
        )
        statuses = _json_object(run.component_status_json)
        context = p2.P2RunContext(
            run_id=run.id,
            project_id=run.project_id,
            episode_id=run.episode_id,
            source_language=project.source_language,
            source_shot_revision_id=run.source_shot_revision_id,
            audio_path=preprocess.audio_path if preprocess else None,
            shots=tuple(
                p2.P2ShotInput(
                    revision_item_id=item.id,
                    original_shot_id=item.original_shot_id,
                    ordinal=item.ordinal,
                    start_us=item.start_us,
                    end_us=item.end_us,
                    duration_us=item.duration_us,
                    reference_clip_path=item.reference_clip_path,
                    thumbnail_path=item.thumbnail_path,
                    keyframes=_keyframes(item.keyframes_json),
                )
                for item in items
            ),
        )

    components: dict[str, legacy.LoadedComponent] = {}
    warnings: list[dict[str, Any]] = []
    for component in _REQUIRED_COMPONENTS:
        entry = statuses.get(component)
        if not isinstance(entry, Mapping):
            raise legacy.BreakdownP2FusionError(
                f"G1 只读重放要求 {component} 已登记 immutable sidecar"
            )
        loaded = legacy._load_one_component(context, entry, component)
        components[component] = loaded
        status = loaded.result.status
        if status in {"FAILED", "NOT_CONFIGURED"}:
            raise legacy.BreakdownP2FusionError(
                f"G1 只读重放拒绝 {component} Provider status={status}"
            )
        if status in _ALLOWED_DEGRADED_STATUSES:
            warnings.append({
                "code": f"{component}_DEGRADED_{status}",
                "message": f"{component} Provider status={status}",
            })

    if components["VLM"].result.status != "READY":
        raise legacy.BreakdownP2FusionError("G1 只读重放要求 READY VLM exact-Shot semantics")

    return legacy.FusionInputBundle(
        context=context,
        components=components,
        warnings=tuple(warnings),
    )


def replay_completed_run(run_id: str) -> dict[str, Any]:
    """Replay candidate continuity against one completed Run; never mutates DB or executes providers."""

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
