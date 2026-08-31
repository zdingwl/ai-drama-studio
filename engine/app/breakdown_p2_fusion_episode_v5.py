"""P2-E5 production Fusion promoted from the accepted G1 read-only replay policy.

E5 preserves E4's immutable-sidecar, anonymous Draft and hard same-Shot cannot-link boundaries,
while promoting the two policies that passed the real completed-Run replay gate:

- corridor-family Scene qualifier drift no longer creates a false cut unless Window Context has a
  DIRECT NEW_SCENE hint or another strong location / INT<->EXT contradiction exists;
- anonymous subject fragments use the accepted replay-v2 continuity graph: Window hints first,
  conservative observation-level gap bridges second, then mutual-best cluster bridges based on
  stable visual consensus and shared same-Shot co-star cannot-link evidence.

This module still produces only Scene-scoped anonymous LocalSubjects. LocalSubject != Character;
Character V10.1, explicit Shot assignment and Final Asset gates remain untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from engine.app import breakdown_g1_fusion_replay_v1 as accepted_scene
from engine.app import breakdown_g1_fusion_replay_v2 as accepted_subject
from engine.app import breakdown_p2_fusion_episode_v2 as e1
from engine.app import breakdown_p2_fusion_episode_v4 as e4
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownRun,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
)

FUSION_PROFILE = "breakdown-p2-fusion-episode-context-e5-v1"
FUSION_VERSION = "1"
BASE_FUSION_PROFILE = e4.FUSION_PROFILE
SCENE_SEGMENTATION_POLICY = accepted_scene.SCENE_POLICY
SUBJECT_CONTINUITY_POLICY = accepted_subject.SUBJECT_POLICY
OBSERVATION_GAP_POLICY = accepted_scene.SUBJECT_POLICY
SUBJECT_HINT_POLICY = e4.SUBJECT_HINT_POLICY
STABLE_APPEARANCE_POLICY = "stable-appearance-gap-plus-cluster-bridge-v2"
MAX_GAP_SHOTS = accepted_scene.MAX_GAP_SHOTS


@dataclass(frozen=True)
class SubjectContinuityStats:
    observation_count: int
    cluster_count: int
    merged_cluster_count: int
    subject_hint_count: int
    cluster_bridge_union_count: int
    final_same_shot_conflict_count: int


def _continuity_plan_details(
    shots: Sequence[p2.P2ShotInput],
    vlm_by_shot: Mapping[str, p2.P2EvidenceRecord],
    window_summaries: Sequence[Mapping[str, Any]],
) -> list[e1._ScenePlanDetail]:
    return [
        e1._ScenePlanDetail(plan=plan, anchor=anchor)
        for plan, anchor in accepted_scene._candidate_scene_plans(
            shots,
            vlm_by_shot,
            window_summaries,
        )
    ]


def _continuity_segment_plans(
    shots: Sequence[p2.P2ShotInput],
    vlm_by_shot: Mapping[str, p2.P2EvidenceRecord],
    window_summaries: Sequence[Mapping[str, Any]],
) -> list[Any]:
    return [item.plan for item in _continuity_plan_details(shots, vlm_by_shot, window_summaries)]


def _build_subject_cluster_keys(
    segment_plans: Sequence[Any],
    window_summaries: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[tuple[str, str], str],
    dict[str, list[dict[str, Any]]],
    SubjectContinuityStats,
]:
    """Convert the accepted replay-v2 clusters into stable keys consumed by the P1 writer."""

    final_keys: dict[tuple[str, str], str] = {}
    cluster_members: dict[str, list[dict[str, Any]]] = {}
    observation_count = 0
    cluster_count = 0
    merged_cluster_count = 0
    cluster_bridge_union_count = 0
    final_same_shot_conflict_count = 0

    for segment_plan in segment_plans:
        observations = e4._observations_for_plan(segment_plan)
        observation_count += len(observations)
        clusters, conflicts = accepted_subject._candidate_clusters(segment_plan, window_summaries)
        final_same_shot_conflict_count += int(conflicts)
        if conflicts:
            raise legacy.BreakdownP2FusionError(
                "E5 fail closed：accepted replay policy produced a same-Shot cluster conflict"
            )

        if clusters:
            try:
                cluster_bridge_union_count += int(clusters[0].get("accepted_cluster_bridge_count") or 0)
            except (TypeError, ValueError):
                pass

        mapped_nodes: set[tuple[str, str]] = set()
        for cluster in clusters:
            raw_members = cluster.get("source_members")
            members = [item for item in raw_members if isinstance(item, Mapping)] if isinstance(raw_members, list) else []
            members.sort(key=lambda item: (
                int(item.get("shot_ordinal") or 0),
                str(item.get("revision_item_id") or ""),
                str(item.get("label") or ""),
            ))
            if not members:
                continue

            cluster_count += 1
            if len(members) > 1:
                merged_cluster_count += 1
            first = members[0]
            first_revision_item_id = str(first.get("revision_item_id") or "").strip()
            first_label = str(first.get("label") or "").strip()
            if not first_revision_item_id or not first_label:
                raise legacy.BreakdownP2FusionError("E5 cluster member missing revision_item_id/label")
            key = (
                f"e5:{first_revision_item_id}:{first_label}"
                if len(members) > 1
                else f"shot:{first_revision_item_id}:{first_label}"
            )

            rows: list[dict[str, Any]] = []
            for member in members:
                revision_item_id = str(member.get("revision_item_id") or "").strip()
                label = str(member.get("label") or "").strip()
                if not revision_item_id or not label:
                    continue
                node = (revision_item_id, label)
                if node in mapped_nodes:
                    raise legacy.BreakdownP2FusionError("E5 anonymous observation mapped to multiple clusters")
                mapped_nodes.add(node)
                final_keys[node] = key
                rows.append({
                    "shot_revision_item_id": revision_item_id,
                    "shot_ordinal": int(member.get("shot_ordinal") or 0),
                    "source_label": label,
                    "appearance_summary": str(member.get("appearance_summary") or ""),
                })
            cluster_members[key] = rows

        expected_nodes = {item.node_id for item in observations}
        if mapped_nodes != expected_nodes:
            missing = len(expected_nodes.difference(mapped_nodes))
            extra = len(mapped_nodes.difference(expected_nodes))
            raise legacy.BreakdownP2FusionError(
                f"E5 anonymous cluster coverage mismatch: missing={missing}, extra={extra}"
            )

    return final_keys, cluster_members, SubjectContinuityStats(
        observation_count=observation_count,
        cluster_count=cluster_count,
        merged_cluster_count=merged_cluster_count,
        subject_hint_count=len(e4._window_subject_hints(window_summaries)),
        cluster_bridge_union_count=cluster_bridge_union_count,
        final_same_shot_conflict_count=final_same_shot_conflict_count,
    )


def _rewrite_subject_metadata(
    session: Any,
    *,
    run_id: str,
    subject_keys: Mapping[tuple[str, str], str],
    cluster_members: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    drafts = {
        item.id: item
        for item in session.scalars(
            select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run_id)
        ).all()
    }
    presences = list(session.scalars(
        select(ShotLocalSubject).where(ShotLocalSubject.run_id == run_id)
    ).all())
    members_by_local: dict[str, list[tuple[str, str, str]]] = {}
    for presence in presences:
        draft = drafts.get(presence.shot_draft_id)
        if draft is None:
            continue
        search_hint = e1._json_object(presence.search_hint_json)
        label = str(search_hint.get("source_vlm_label") or "").strip()
        key = subject_keys.get((draft.source_shot_revision_item_id, label))
        if key:
            members_by_local.setdefault(presence.local_subject_id, []).append(
                (draft.source_shot_revision_item_id, label, key)
            )

    for local in session.scalars(
        select(LocalSubject).where(LocalSubject.run_id == run_id)
    ).all():
        rows = members_by_local.get(local.id, [])
        cluster_key = rows[0][2] if rows else None
        metadata = e1._json_object(local.appearance_json)
        metadata.update({
            "fusion_profile": FUSION_PROFILE,
            "link_policy": SUBJECT_CONTINUITY_POLICY,
            "subject_hint_policy": SUBJECT_HINT_POLICY,
            "observation_gap_policy": OBSERVATION_GAP_POLICY,
            "stable_appearance_policy": STABLE_APPEARANCE_POLICY,
            "same_shot_cannot_link": True,
            "cluster_key": cluster_key,
            "source_members": list(cluster_members.get(cluster_key, ())) if cluster_key else [],
        })
        local.appearance_json = e1._json_text(metadata)


def _rewrite_e5_metadata(
    session: Any,
    *,
    run: BreakdownRun,
    stats: SubjectContinuityStats,
) -> None:
    statuses = e1._json_object(run.component_status_json)
    fusion_status = statuses.get("FUSION")
    if not isinstance(fusion_status, dict):
        fusion_status = {}
    fusion_status.update({
        "profile": FUSION_PROFILE,
        "version": FUSION_VERSION,
        "base_profile": BASE_FUSION_PROFILE,
        "scene_segmentation_policy": SCENE_SEGMENTATION_POLICY,
        "subject_continuity": {
            "policy": SUBJECT_CONTINUITY_POLICY,
            "observation_gap_policy": OBSERVATION_GAP_POLICY,
            "observation_count": stats.observation_count,
            "cluster_count": stats.cluster_count,
            "merged_cluster_count": stats.merged_cluster_count,
            "subject_hint_count": stats.subject_hint_count,
            "cluster_bridge_union_count": stats.cluster_bridge_union_count,
            "final_same_shot_conflict_count": stats.final_same_shot_conflict_count,
        },
    })
    statuses["FUSION"] = fusion_status

    providers = e1._json_object(run.provider_metadata_json)
    previous = providers.get("p2_fusion")
    p2_fusion = dict(previous) if isinstance(previous, Mapping) else {}
    p2_fusion.update({
        "profile": FUSION_PROFILE,
        "version": FUSION_VERSION,
        "base_profile": BASE_FUSION_PROFILE,
        "scene_segmentation_policy": SCENE_SEGMENTATION_POLICY,
        "subject_continuity_policy": SUBJECT_CONTINUITY_POLICY,
        "subject_hint_policy": SUBJECT_HINT_POLICY,
        "observation_gap_policy": OBSERVATION_GAP_POLICY,
        "stable_appearance_policy": STABLE_APPEARANCE_POLICY,
        "same_shot_cannot_link": "hard",
        "local_subject_semantics": "anonymous-scene-scoped-not-character",
        "promotion_source": "g1-read-only-replay-v2-real-accepted",
    })
    providers["p2_fusion"] = p2_fusion

    for segment in session.scalars(
        select(SceneSegmentDraft).where(SceneSegmentDraft.run_id == run.id)
    ).all():
        metadata = e1._json_object(segment.metadata_json)
        metadata["fusion_profile"] = FUSION_PROFILE
        metadata["segmentation_policy"] = SCENE_SEGMENTATION_POLICY
        segment.metadata_json = e1._json_text(metadata)
    for draft in session.scalars(
        select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)
    ).all():
        metadata = e1._json_object(draft.model_metadata_json)
        metadata["fusion_profile"] = FUSION_PROFILE
        metadata["scene_context_policy"] = SCENE_SEGMENTATION_POLICY
        metadata["subject_continuity_policy"] = SUBJECT_CONTINUITY_POLICY
        draft.model_metadata_json = e1._json_text(metadata)

    run.component_status_json = e1._json_text(statuses)
    run.provider_metadata_json = e1._json_text(providers)


def fuse_breakdown_run(run_id: str) -> BreakdownRun:
    """E5 production entry: immutable ASR/OCR/VLM sidecars -> accepted continuity -> P1 Draft."""

    try:
        source_bundle = legacy.load_fusion_inputs(run_id)
        projection_bundle = e1._episode_projection_bundle(source_bundle)
        window_summaries = e4._window_summaries(source_bundle)
        shots_by_id = {shot.revision_item_id: shot for shot in source_bundle.context.shots}
        vlm_by_shot = {
            item.shot_revision_item_id: item
            for item in source_bundle.components["VLM"].result.evidence
            if item.source_type.strip().upper() == "VLM_OUTPUT"
            and item.shot_revision_item_id in shots_by_id
        }
        segment_plans = _continuity_segment_plans(
            source_bundle.context.shots,
            vlm_by_shot,
            window_summaries,
        )
        subject_keys, cluster_members, stats = _build_subject_cluster_keys(
            segment_plans,
            window_summaries,
        )

        def e5_segment_plans(
            shots: Sequence[p2.P2ShotInput],
            records: Mapping[str, p2.P2EvidenceRecord],
        ) -> list[Any]:
            return _continuity_segment_plans(shots, records, window_summaries)

        def e5_plan_details(
            shots: Sequence[p2.P2ShotInput],
            records: Mapping[str, p2.P2EvidenceRecord],
        ) -> list[e1._ScenePlanDetail]:
            return _continuity_plan_details(shots, records, window_summaries)

        def e5_appearance_key(
            subject: Mapping[str, Any],
            shot: p2.P2ShotInput,
            label: str,
            ambiguous_appearances: set[str] | None = None,
        ) -> str:
            del subject, ambiguous_appearances
            return subject_keys.get(
                (shot.revision_item_id, label),
                f"shot:{shot.revision_item_id}:{label}",
            )

        with e1._FUSION_PATCH_LOCK:
            original_segment_plans = legacy._segment_plans
            original_appearance_key = legacy._appearance_key
            original_plan_details = e1._continuity_plan_details
            legacy._segment_plans = e5_segment_plans
            legacy._appearance_key = e5_appearance_key
            e1._continuity_plan_details = e5_plan_details
            try:
                raw_warnings, _generated_counts = legacy._write_fused_draft(projection_bundle)

                warnings = [
                    dict(item) for item in raw_warnings
                    if str(item.get("code") or "") != "ASR_CROSS_SHOT_TEXT_FALLBACK"
                ]
                if stats.observation_count >= 4 and stats.merged_cluster_count == 0:
                    warnings.append({
                        "code": "E5_SUBJECT_CONTINUITY_UNRESOLVED",
                        "message": "E5 未形成任何跨镜匿名人物连续簇；请检查 Window hints / stable appearance Evidence",
                    })

                with studio_v2.get_session() as session:
                    run = session.get(BreakdownRun, run_id)
                    if run is None:
                        raise LookupError("Breakdown Run 不存在")
                    if run.status != "PROCESSING":
                        raise legacy.BreakdownP2FusionError(
                            f"E5 post-Fusion 只允许处理 PROCESSING Run，当前状态为 {run.status}"
                        )
                    e1._rewrite_dialogue_events(session, run_id=run_id, source_bundle=source_bundle)
                    e1._rewrite_scene_rows(session, run_id=run_id, source_bundle=source_bundle)
                    _rewrite_subject_metadata(
                        session,
                        run_id=run_id,
                        subject_keys=subject_keys,
                        cluster_members=cluster_members,
                    )
                    e1._rewrite_run_metadata(session, run=run, warnings=warnings)
                    _rewrite_e5_metadata(session, run=run, stats=stats)
                    session.commit()
            finally:
                legacy._segment_plans = original_segment_plans
                legacy._appearance_key = original_appearance_key
                e1._continuity_plan_details = original_plan_details

        return breakdown_service_v1.publish_breakdown_run(
            run_id,
            warnings=warnings or None,
        )
    except Exception as exc:
        legacy._safe_fail_run(run_id, exc)
        raise


__all__ = [
    "BASE_FUSION_PROFILE",
    "FUSION_PROFILE",
    "FUSION_VERSION",
    "MAX_GAP_SHOTS",
    "OBSERVATION_GAP_POLICY",
    "SCENE_SEGMENTATION_POLICY",
    "STABLE_APPEARANCE_POLICY",
    "SUBJECT_CONTINUITY_POLICY",
    "SUBJECT_HINT_POLICY",
    "SubjectContinuityStats",
    "_build_subject_cluster_keys",
    "_continuity_plan_details",
    "_continuity_segment_plans",
    "fuse_breakdown_run",
]
