"""Read-only G1 Fusion replay over frozen P2 sidecars.

This module never executes ASR/OCR/VLM and never writes Breakdown Draft/Final rows.
It replays candidate Scene/anonymous-subject continuity policies in memory so a completed
Fast Grounded Run can be evaluated before the policy is promoted to production Fusion.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Mapping, Sequence

from engine.app import breakdown_p2_fusion_episode_v2 as e1
from engine.app import breakdown_p2_fusion_episode_v4 as e4
from engine.app import breakdown_p2_fusion_v1 as legacy

REPLAY_PROFILE = "breakdown-g1-fusion-replay-v1"
SCENE_POLICY = "corridor-family-qualifier-drift-with-direct-new-scene-v1"
SUBJECT_POLICY = "stable-appearance-gap-bridge-hard-same-shot-cannot-link-v1"
MAX_GAP_SHOTS = 6

_CORRIDOR_MARKERS = (
    "走廊",
    "楼道",
    "过道",
    "hallway",
    "corridor",
)


@dataclass(frozen=True)
class ReplayScene:
    ordinal: int
    start_us: int
    end_us: int
    shot_ordinals: tuple[int, ...]
    location_hint: str | None
    interior_exterior: str
    local_subjects: tuple[dict[str, Any], ...]
    same_shot_cluster_conflicts: int


def _spatial_family(hint: Any) -> str | None:
    key = str(getattr(hint, "location_key", "") or "").lower()
    if any(marker in key for marker in _CORRIDOR_MARKERS):
        return "CORRIDOR"
    return None


def _locations_compatible(left: Any, right: Any) -> bool:
    if e1._locations_compatible(left, right):
        return True
    left_family = _spatial_family(left)
    right_family = _spatial_family(right)
    return bool(left_family and left_family == right_family)


def _strong_scene_change(current: Any, candidate: Any) -> bool:
    if (
        not e1._weak_location(current)
        and not e1._weak_location(candidate)
        and not _locations_compatible(current, candidate)
    ):
        return True
    if (
        current.interior_exterior in {"INT", "EXT"}
        and candidate.interior_exterior in {"INT", "EXT"}
        and current.interior_exterior != candidate.interior_exterior
    ):
        return True
    return False


def _merge_anchor(current: Any, candidate: Any) -> Any:
    location = current.location
    location_key = current.location_key
    if e1._weak_location(current) and not e1._weak_location(candidate):
        location, location_key = candidate.location, candidate.location_key
    elif (
        not e1._weak_location(candidate)
        and _locations_compatible(current, candidate)
        and _spatial_family(current) is None
        and len(candidate.location_key) > len(current.location_key)
    ):
        # Keep the first corridor label when only its qualifier drifts
        # ("公寓走廊" vs "酒店走廊"); for normal compatible specificity,
        # still prefer the more specific hint ("病房" -> "医院病房").
        location, location_key = candidate.location, candidate.location_key

    interior = current.interior_exterior
    if interior == "UNKNOWN" and candidate.interior_exterior != "UNKNOWN":
        interior = candidate.interior_exterior

    time_of_day = current.time_of_day
    if not time_of_day and candidate.time_of_day:
        time_of_day = candidate.time_of_day

    return e1._SceneHint(location, location_key, interior, time_of_day)


def _direct_new_scene_ordinals(window_summaries: Sequence[Mapping[str, Any]]) -> set[int]:
    result: set[int] = set()
    for window in window_summaries:
        raw_hints = window.get("shot_scene_hints") if isinstance(window, Mapping) else None
        if not isinstance(raw_hints, list):
            continue
        for hint in raw_hints:
            if not isinstance(hint, Mapping):
                continue
            continuity = str(hint.get("scene_continuity") or "").strip().upper()
            basis = str(hint.get("scene_basis") or "").strip().upper()
            if continuity != "NEW_SCENE" or basis != "DIRECT":
                continue
            try:
                ordinal = int(hint.get("ordinal"))
            except (TypeError, ValueError):
                continue
            if ordinal > 0:
                result.add(ordinal)
    return result


def _candidate_scene_plans(
    shots: Sequence[Any],
    vlm_by_shot: Mapping[str, Any],
    window_summaries: Sequence[Mapping[str, Any]],
) -> list[tuple[Any, Any]]:
    details: list[tuple[Any, Any]] = []
    current_plan: Any | None = None
    current_anchor = e1._SceneHint(None, "", "UNKNOWN", None)
    direct_new_scene = _direct_new_scene_ordinals(window_summaries)

    for shot in shots:
        semantic = legacy._semantic(vlm_by_shot.get(shot.revision_item_id))
        hint = e1._scene_hint(semantic)
        force_direct_cut = current_plan is not None and int(shot.ordinal) in direct_new_scene
        if current_plan is None or force_direct_cut or _strong_scene_change(current_anchor, hint):
            current_plan = legacy._SegmentPlan(index=len(details) + 1)
            current_anchor = hint
            details.append((current_plan, current_anchor))
        else:
            current_anchor = _merge_anchor(current_anchor, hint)
            details[-1] = (current_plan, current_anchor)
        current_plan.shots.append(shot)
        current_plan.semantics.append(semantic)
    return details


def _gap_rule(distance: int) -> tuple[float, int, float] | None:
    if distance <= 0 or distance > MAX_GAP_SHOTS:
        return None
    if distance == 1:
        return 4.0, 2, 0.0
    if distance == 2:
        return 4.5, 2, 0.25
    if distance <= 4:
        return 5.25, 3, 0.75
    return 5.75, 3, 1.0


def _candidate_fallback_pairs(
    observations: Sequence[e4.SubjectObservation],
) -> list[tuple[int, int]]:
    by_ordinal: dict[int, list[int]] = {}
    for index, item in enumerate(observations):
        by_ordinal.setdefault(item.shot_ordinal, []).append(index)

    ordinals = sorted(by_ordinal)
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    for left_pos, left_ordinal in enumerate(ordinals):
        for right_ordinal in ordinals[left_pos + 1:]:
            distance = right_ordinal - left_ordinal
            rule = _gap_rule(distance)
            if rule is None:
                if distance > MAX_GAP_SHOTS:
                    break
                continue
            threshold, min_strong, min_margin = rule
            left_indexes = by_ordinal[left_ordinal]
            right_indexes = by_ordinal[right_ordinal]
            scores = {
                (left, right): e4._appearance_similarity(
                    observations[left].appearance_summary,
                    observations[right].appearance_summary,
                )
                for left in left_indexes
                for right in right_indexes
            }

            for left in left_indexes:
                left_ranked = sorted(
                    ((scores[(left, right)][0], right) for right in right_indexes),
                    reverse=True,
                )
                if not left_ranked:
                    continue
                best_score, best_right = left_ranked[0]
                second_left = left_ranked[1][0] if len(left_ranked) > 1 else -math.inf

                right_ranked = sorted(
                    ((scores[(candidate, best_right)][0], candidate) for candidate in left_indexes),
                    reverse=True,
                )
                if not right_ranked or right_ranked[0][1] != left:
                    continue
                second_right = right_ranked[1][0] if len(right_ranked) > 1 else -math.inf
                _score, strong_count = scores[(left, best_right)]

                if not math.isfinite(best_score) or best_score < threshold or strong_count < min_strong:
                    continue
                if math.isfinite(second_left) and best_score - second_left < min_margin:
                    continue
                if math.isfinite(second_right) and best_score - second_right < min_margin:
                    continue
                pair = (left, best_right)
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
    return pairs


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
            uf.union(left, right)

    for left, right in _candidate_fallback_pairs(observations):
        uf.union(left, right)

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
        clusters.append(
            {
                "display_label": f"人物{chr(64 + cluster_index) if cluster_index <= 26 else cluster_index}",
                "shot_ordinals": sorted({int(item["shot_ordinal"]) for item in members}),
                "source_labels": sorted({str(item["label"]) for item in members}),
                "source_members": members,
                "same_shot_conflicts": max(0, duplicate_count),
            }
        )
    return clusters, conflicts


def replay_run(run_id: str) -> dict[str, Any]:
    bundle = legacy.load_fusion_inputs(run_id)
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
        if item.source_type.strip().upper() == "VLM_OUTPUT"
        and item.shot_revision_item_id
    }
    details = _candidate_scene_plans(bundle.context.shots, vlm_by_shot, window_summaries)

    scenes: list[dict[str, Any]] = []
    total_conflicts = 0
    for ordinal, (plan, anchor) in enumerate(details, start=1):
        clusters, conflicts = _candidate_clusters(plan, window_summaries)
        total_conflicts += conflicts
        scenes.append(
            {
                "ordinal": ordinal,
                "start_us": int(plan.shots[0].start_us),
                "end_us": int(plan.shots[-1].end_us),
                "shot_ordinals": [int(shot.ordinal) for shot in plan.shots],
                "location_hint": anchor.location,
                "interior_exterior": anchor.interior_exterior,
                "local_subject_count": len(clusters),
                "local_subjects": clusters,
                "same_shot_cluster_conflicts": conflicts,
            }
        )

    return {
        "schema_version": REPLAY_PROFILE,
        "kind": "read_only_fusion_replay",
        "run_id": bundle.context.run_id,
        "episode_id": bundle.context.episode_id,
        "source_shot_revision_id": bundle.context.source_shot_revision_id,
        "providers_executed": [],
        "mutates_breakdown_run": False,
        "mutates_final_assets": False,
        "policies": {
            "scene": SCENE_POLICY,
            "subject_continuity": SUBJECT_POLICY,
            "max_gap_shots": MAX_GAP_SHOTS,
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


def format_summary(payload: Mapping[str, Any]) -> str:
    lines = [
        "=== G1 Fusion 只读重放（不运行模型、不写正式 Draft）===",
        f"Run: {payload.get('run_id')}",
        f"Episode: {payload.get('episode_id')}",
        "providers_executed=[] | mutates_breakdown_run=false | mutates_final_assets=false",
        f"Candidate Scenes: {payload.get('scene_count')}",
    ]
    for scene in payload.get("scenes", []):
        if not isinstance(scene, Mapping):
            continue
        shots = scene.get("shot_ordinals") or []
        shot_text = f"{shots[0]}-{shots[-1]}" if shots else "-"
        lines.append(
            "Scene {ordinal}: shots={shots} | count={count} | LocalSubjects={subjects} | "
            "location={location} | conflicts={conflicts}".format(
                ordinal=scene.get("ordinal"),
                shots=shot_text,
                count=len(shots),
                subjects=scene.get("local_subject_count"),
                location=scene.get("location_hint") or "UNKNOWN",
                conflicts=scene.get("same_shot_cluster_conflicts"),
            )
        )
        for subject in scene.get("local_subjects", []):
            if not isinstance(subject, Mapping):
                continue
            lines.append(
                "  - {label} | shots={shots} | source_labels={labels} | same-shot-conflicts={conflicts}".format(
                    label=subject.get("display_label"),
                    shots=",".join(str(value) for value in subject.get("shot_ordinals", [])),
                    labels=",".join(str(value) for value in subject.get("source_labels", [])),
                    conflicts=subject.get("same_shot_conflicts"),
                )
            )
    lines.append(f"[Hard safety] same_shot_cluster_conflicts={payload.get('same_shot_cluster_conflicts')}")
    lines.append("This is candidate replay only; it does not promote G1/P2.6 to PASS.")
    return "\n".join(lines)
