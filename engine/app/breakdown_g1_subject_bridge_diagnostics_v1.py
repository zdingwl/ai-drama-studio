"""Read-only cluster bridge diagnostics for G1 anonymous subject continuity.

The current G1 replay intentionally stays conservative. This diagnostic explains why already-formed
anonymous LocalSubject fragments did or did not reconnect without changing any production or replay
merge policy. It reads only the in-memory replay payload built from immutable completed-run sidecars.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Mapping, Sequence

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed
from engine.app import breakdown_p2_fusion_episode_v4 as e4

DIAGNOSTIC_SCHEMA = "breakdown-g1-subject-bridge-diagnostics-v1"
MAX_DIAGNOSTIC_GAP_SHOTS = 6


def _members(cluster: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = cluster.get("source_members")
    return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _shot_set(cluster: Mapping[str, Any]) -> set[int]:
    result: set[int] = set()
    for value in cluster.get("shot_ordinals") or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _cluster_gap(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    a = sorted(_shot_set(left))
    b = sorted(_shot_set(right))
    if not a or not b:
        return 10**9
    if a[-1] < b[0]:
        return b[0] - a[-1]
    if b[-1] < a[0]:
        return a[0] - b[-1]
    return 0


def _cluster_profile(cluster: Mapping[str, Any]) -> dict[str, Any]:
    members = _members(cluster)
    genders: set[str] = set()
    feature_counts: Counter[str] = Counter()
    appearances: list[dict[str, Any]] = []
    seen_appearance: set[str] = set()
    for member in members:
        appearance = str(member.get("appearance_summary") or "").strip()
        gender = e4._gender(appearance)
        if gender:
            genders.add(gender)
        for feature in e4._stable_features(appearance):
            feature_counts[feature] += 1
        if appearance and appearance not in seen_appearance and len(appearances) < 4:
            seen_appearance.add(appearance)
            appearances.append({
                "shot_ordinal": member.get("shot_ordinal"),
                "text": appearance[:180],
            })
    observation_count = max(1, len(members))
    consensus_min = 1 if observation_count <= 2 else max(2, math.ceil(observation_count * 0.35))
    consensus = [
        feature for feature, count in sorted(feature_counts.items())
        if count >= consensus_min
    ]
    return {
        "label": str(cluster.get("display_label") or "?"),
        "shot_ordinals": sorted(_shot_set(cluster)),
        "shot_set": _shot_set(cluster),
        "member_count": len(members),
        "genders": sorted(genders),
        "consensus_features": consensus,
        "feature_counts": dict(sorted(feature_counts.items())),
        "appearance_examples": appearances,
        "members": members,
    }


def _pairwise_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for left_member in left.get("members") or []:
        for right_member in right.get("members") or []:
            score, strong = e4._appearance_similarity(
                left_member.get("appearance_summary"),
                right_member.get("appearance_summary"),
            )
            if not math.isfinite(score):
                continue
            rows.append({
                "score": round(float(score), 3),
                "strong_count": int(strong),
                "left_shot": left_member.get("shot_ordinal"),
                "right_shot": right_member.get("shot_ordinal"),
                "left_appearance": str(left_member.get("appearance_summary") or "")[:140],
                "right_appearance": str(right_member.get("appearance_summary") or "")[:140],
            })
    rows.sort(key=lambda item: (item["score"], item["strong_count"]), reverse=True)
    top = rows[:3]
    return {
        "finite_pair_count": len(rows),
        "max_score": top[0]["score"] if top else None,
        "top3_mean": round(sum(item["score"] for item in top) / len(top), 3) if top else None,
        "support_4_strong2": sum(
            1 for item in rows
            if float(item["score"]) >= 4.0 and int(item["strong_count"]) >= 2
        ),
        "support_3_strong2": sum(
            1 for item in rows
            if float(item["score"]) >= 3.0 and int(item["strong_count"]) >= 2
        ),
        "best_pairs": top,
    }


def _bridge_candidates(clusters: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    profiles = [_cluster_profile(cluster) for cluster in clusters]
    bridges: list[dict[str, Any]] = []
    for left_index, left in enumerate(profiles):
        for right_index in range(left_index + 1, len(profiles)):
            right = profiles[right_index]
            shared_shots = sorted(left["shot_set"].intersection(right["shot_set"]))
            gap = _cluster_gap(left, right)
            if shared_shots or gap > MAX_DIAGNOSTIC_GAP_SHOTS:
                continue
            left_genders = set(left["genders"])
            right_genders = set(right["genders"])
            gender_conflict = bool(left_genders and right_genders and left_genders.isdisjoint(right_genders))
            common_neighbors: list[str] = []
            for other_index, other in enumerate(profiles):
                if other_index in {left_index, right_index}:
                    continue
                if left["shot_set"].intersection(other["shot_set"]) and right["shot_set"].intersection(other["shot_set"]):
                    common_neighbors.append(str(other["label"]))
            similarity = _pairwise_similarity(left, right)
            top3 = similarity["top3_mean"] if similarity["top3_mean"] is not None else -100.0
            rank_score = (
                float(top3)
                + 1.5 * len(common_neighbors)
                + 0.75 * int(similarity["support_4_strong2"])
                + (1.0 if gap <= 1 else 0.5 if gap <= 3 else 0.0)
                - (100.0 if gender_conflict else 0.0)
            )
            bridges.append({
                "left": left["label"],
                "right": right["label"],
                "gap_shots": gap,
                "gender_conflict": gender_conflict,
                "common_cannot_link_neighbors": common_neighbors,
                "rank_score": round(rank_score, 3),
                **similarity,
            })
    bridges.sort(key=lambda item: item["rank_score"], reverse=True)
    public_profiles = [
        {key: value for key, value in profile.items() if key not in {"shot_set", "members"}}
        for profile in profiles
    ]
    return public_profiles, bridges


def inspect_run(run_id: str) -> dict[str, Any]:
    replay = completed.replay_completed_run(run_id)
    scenes: list[dict[str, Any]] = []
    for scene in replay.get("scenes", []):
        if not isinstance(scene, Mapping):
            continue
        clusters = [
            item for item in scene.get("local_subjects", [])
            if isinstance(item, Mapping)
        ]
        profiles, bridges = _bridge_candidates(clusters)
        scenes.append({
            "ordinal": scene.get("ordinal"),
            "shot_ordinals": list(scene.get("shot_ordinals") or []),
            "location_hint": scene.get("location_hint"),
            "local_subject_count": len(clusters),
            "profiles": profiles,
            "bridge_candidates": bridges,
        })
    return {
        "schema_version": DIAGNOSTIC_SCHEMA,
        "run_id": replay.get("run_id"),
        "episode_id": replay.get("episode_id"),
        "providers_executed": [],
        "mutates_breakdown_run": False,
        "mutates_final_assets": False,
        "scenes": scenes,
    }


def _fmt_score(value: Any) -> str:
    return "-" if value is None else f"{float(value):.2f}"


def format_summary(payload: Mapping[str, Any], *, scene_ordinal: int | None = None, top: int = 15) -> str:
    lines = [
        "=== G1 人物碎片 Bridge 诊断（只读，不自动合并）===",
        f"Run: {payload.get('run_id')}",
        "providers_executed=[] | mutates_breakdown_run=false | mutates_final_assets=false",
    ]
    matched = False
    for scene in payload.get("scenes", []):
        if not isinstance(scene, Mapping):
            continue
        ordinal = int(scene.get("ordinal") or 0)
        if scene_ordinal is not None and ordinal != scene_ordinal:
            continue
        matched = True
        shots = list(scene.get("shot_ordinals") or [])
        shot_text = f"{shots[0]}-{shots[-1]}" if shots else "-"
        lines.append(
            f"\n[Scene {ordinal}] shots={shot_text} | LocalSubjects={scene.get('local_subject_count')} | "
            f"location={scene.get('location_hint') or 'UNKNOWN'}"
        )
        for profile in scene.get("profiles", []):
            if not isinstance(profile, Mapping):
                continue
            genders = ",".join(str(v) for v in profile.get("genders", [])) or "?"
            features = ", ".join(str(v) for v in profile.get("consensus_features", [])) or "-"
            lines.append(
                f"  {profile.get('label')} | shots={','.join(str(v) for v in profile.get('shot_ordinals', []))} "
                f"| gender={genders} | consensus={features}"
            )
            for example in profile.get("appearance_examples", [])[:2]:
                if isinstance(example, Mapping):
                    lines.append(f"    @{example.get('shot_ordinal')}: {example.get('text')}")
        lines.append("  [Top bridge candidates]")
        bridges = [item for item in scene.get("bridge_candidates", []) if isinstance(item, Mapping)]
        for bridge in bridges[:max(1, int(top))]:
            common = ",".join(str(v) for v in bridge.get("common_cannot_link_neighbors", [])) or "-"
            lines.append(
                "    {left}<->{right} | gap={gap} | max={max_score} | top3={top3} | "
                "support4/2={support} | common-cannot-link={common} | gender-conflict={conflict}".format(
                    left=bridge.get("left"),
                    right=bridge.get("right"),
                    gap=bridge.get("gap_shots"),
                    max_score=_fmt_score(bridge.get("max_score")),
                    top3=_fmt_score(bridge.get("top3_mean")),
                    support=bridge.get("support_4_strong2"),
                    common=common,
                    conflict="YES" if bridge.get("gender_conflict") else "NO",
                )
            )
            best = bridge.get("best_pairs") or []
            if best and isinstance(best[0], Mapping):
                item = best[0]
                lines.append(
                    f"      best {item.get('left_shot')}<->{item.get('right_shot')} "
                    f"score={_fmt_score(item.get('score'))} strong={item.get('strong_count')}"
                )
    if scene_ordinal is not None and not matched:
        lines.append(f"Scene {scene_ordinal} not found")
    lines.append("\nThis diagnostic only explains evidence; it does not change the replay or production merge policy.")
    return "\n".join(lines)
