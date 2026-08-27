"""Character V10.1 shot-level identity recovery.

The global identity resolver is deliberately conservative at single Person-Evidence level.
That is correct for creating a Character, but it can leave a short Shot unbound when
several individually-ambiguous observations from one Track consistently match the same
already-confirmed identity.

This module performs a second, track-level attachment pass *after* Final Character
identity classes are confirmed:

UNRESOLVED Track observations
-> compare against each RESOLVED identity gallery
-> aggregate repeated Person-ReID support across time and gallery Shots
-> require a unique winner and preserve cannot-link / high-quality face conflicts
-> move only that Track into the confirmed identity

It never creates a new Character and never changes the >=3-shot identity confirmation
gate.  Its only purpose is to recover "known Character is visibly present in this Shot"
without treating one weak crop as a new identity.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from engine.app import character_gallery_v10 as gallery_v10
from engine.app import character_visual_v5 as v5
from engine.app.character_identity_v10 import (
    AMBIGUITY_MARGIN,
    APPEARANCE_SUPPORT,
    FACE_CONFLICT,
    FACE_CONFLICT_MIN_SCORE,
    REID_AMBIGUOUS,
)
from engine.app.character_person_features_v9 import feature_channel_scores

MIN_TRACK_OBSERVATIONS = 3
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
MIN_SUPPORTING_OBSERVATIONS = 2
WINNER_MARGIN = max(0.07, AMBIGUITY_MARGIN)
RISKY_CLASSES = {"CONTAMINATED", "PARTIAL"}


def _instance_id(observation: Any) -> str:
    return str(getattr(observation, "instance_id", "") or "")


def _cannot_link(left: Any, right: Any) -> bool:
    left_id = _instance_id(left)
    right_id = _instance_id(right)
    if not left_id or not right_id:
        return False
    left_forbidden = {str(value) for value in (getattr(left, "cannot_link_instance_ids", []) or [])}
    right_forbidden = {str(value) for value in (getattr(right, "cannot_link_instance_ids", []) or [])}
    return right_id in left_forbidden or left_id in right_forbidden


def _bundle(observation: Any) -> Any | None:
    value = getattr(observation, "person_feature_bundle", None)
    if value is None or getattr(value, "person_reid", None) is None:
        return None
    return value


def _face_conflict(left_bundle: Any, right_bundle: Any, scores: dict[str, float | None]) -> bool:
    face = scores.get("face")
    return bool(
        getattr(left_bundle, "face", None) is not None
        and getattr(right_bundle, "face", None) is not None
        and float(getattr(left_bundle, "face_score", 0.0) or 0.0) >= FACE_CONFLICT_MIN_SCORE
        and float(getattr(right_bundle, "face_score", 0.0) or 0.0) >= FACE_CONFLICT_MIN_SCORE
        and face is not None
        and float(face) <= FACE_CONFLICT
    )


def _gallery_observations(candidate: Any) -> list[Any]:
    representatives = list(getattr(candidate, "gallery", []) or [])
    if not representatives:
        representatives = gallery_v10.select_candidate_gallery(list(getattr(candidate, "tracks", []) or []))
    return [
        representative.observation
        for representative in representatives
        if _bundle(getattr(representative, "observation", None)) is not None
    ]


def _observation_support(observation: Any, gallery: list[Any]) -> tuple[float | None, int, bool]:
    """Return (gallery-aware ReID support, appearance-support channels, hard conflict)."""

    bundle = _bundle(observation)
    if bundle is None:
        return None, 0, False

    by_shot: dict[str, tuple[float, int]] = {}
    for member in gallery:
        if _cannot_link(observation, member):
            return None, 0, True
        member_bundle = _bundle(member)
        if member_bundle is None:
            continue
        scores = feature_channel_scores(bundle, member_bundle)
        if _face_conflict(bundle, member_bundle, scores):
            return None, 0, True
        reid = scores.get("person_reid")
        if reid is None:
            continue
        value = float(reid)
        appearance = sum(
            1
            for name in ("clothing_upper", "clothing_lower", "body_hist", "body_structure")
            if scores.get(name) is not None and float(scores[name]) >= APPEARANCE_SUPPORT
        )
        shot_id = str(getattr(member, "shot_id", ""))
        previous = by_shot.get(shot_id)
        if previous is None or value > previous[0]:
            by_shot[shot_id] = (value, appearance)

    if not by_shot:
        return None, 0, False
    ordered = sorted(by_shot.values(), key=lambda row: row[0], reverse=True)
    # Two independent gallery Shots are more reliable than many near-duplicate images
    # from one Shot.  If only one gallery Shot is available, keep its best score.
    support = median([row[0] for row in ordered[:2]]) if len(ordered) >= 2 else ordered[0][0]
    appearance = max(row[1] for row in ordered[:2])
    return float(support), int(appearance), False


def _track_candidate_score(track: Any, gallery: list[Any]) -> float | None:
    supports: list[float] = []
    appearance_supported = 0
    risky_count = 0
    usable = 0

    for observation in list(getattr(track, "observations", []) or []):
        support, appearance, hard_conflict = _observation_support(observation, gallery)
        if hard_conflict:
            return None
        if support is None or support < REID_AMBIGUOUS:
            continue
        usable += 1
        supports.append(support)
        if appearance >= 1:
            appearance_supported += 1
        if str(getattr(observation, "instance_class", "") or "").upper() in RISKY_CLASSES:
            risky_count += 1

    if usable < MIN_TRACK_OBSERVATIONS:
        return None

    ordered = sorted(supports, reverse=True)
    track_score = float(median(ordered[: min(5, len(ordered))]))
    risky = risky_count >= max(1, usable // 2)
    threshold = RISKY_TRACK_MEDIAN if risky else NORMAL_TRACK_MEDIAN
    supporting = sum(1 for value in supports if value >= threshold)
    if track_score < threshold or supporting < MIN_SUPPORTING_OBSERVATIONS:
        return None
    # Repeated strong ReID can stand alone; otherwise require at least some independent
    # clothing/body support so a weakly similar silhouette cannot silently attach.
    if track_score < STRONG_TRACK_MEDIAN and appearance_supported < MIN_SUPPORTING_OBSERVATIONS:
        return None
    return track_score


def _best_resolved_candidate(track: Any, resolved: list[Any]) -> tuple[Any | None, float | None]:
    scored: list[tuple[float, Any]] = []
    for candidate in resolved:
        gallery = _gallery_observations(candidate)
        if not gallery:
            continue
        score = _track_candidate_score(track, gallery)
        if score is not None:
            scored.append((score, candidate))

    if not scored:
        return None, None
    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best = scored[0]
    if len(scored) > 1 and best_score - scored[1][0] < WINNER_MARGIN:
        return None, None
    return best, best_score


def _refresh_candidate(candidate: Any) -> None:
    tracks = list(getattr(candidate, "tracks", []) or [])
    candidate.face_embedding = v5.mean_vector([
        track.face_embedding for track in tracks if getattr(track, "face_embedding", None) is not None
    ])
    candidate.reid_embedding = v5.mean_vector([
        track.reid_embedding for track in tracks if getattr(track, "reid_embedding", None) is not None
    ])
    candidate.body_hist = v5.mean_vector([
        track.body_hist for track in tracks if getattr(track, "body_hist", None) is not None
    ])
    candidate.gallery = gallery_v10.select_candidate_gallery(tracks)

    metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
    metadata["captured_classified_images"] = len(candidate.gallery)
    metadata["classified_shots"] = len({str(track.shot_id) for track in tracks})
    metadata["instance_classes"] = sorted({
        str(getattr(representative.observation, "instance_class", "UNKNOWN"))
        for representative in candidate.gallery
    })
    candidate.v10_metadata = metadata  # type: ignore[attr-defined]


def recover_unresolved_tracks(candidates: list[Any]) -> list[Any]:
    """Attach repeatedly-consistent unresolved Tracks to existing confirmed identities.

    The pass is fail-closed:
    - no confirmed identities -> no changes;
    - fewer than 3 usable observations -> no recovery;
    - same-sample cannot-link / strong face conflict -> no recovery;
    - ambiguous winner -> no recovery;
    - it never creates a new resolved identity.
    """

    resolved = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "identity_status", "UNRESOLVED")).upper() == "RESOLVED"
    ]
    if not resolved:
        return candidates

    output: list[Any] = list(resolved)
    recovered_by_id: dict[str, list[tuple[str, float]]] = {}

    for candidate in candidates:
        if candidate in resolved:
            continue
        remaining_tracks: list[Any] = []
        for track in list(getattr(candidate, "tracks", []) or []):
            target, score = _best_resolved_candidate(track, resolved)
            if target is None or score is None:
                remaining_tracks.append(track)
                continue
            target.tracks.append(track)
            recovered_by_id.setdefault(str(target.id), []).append((str(track.shot_id), float(score)))

        if remaining_tracks:
            candidate.tracks = remaining_tracks
            candidate.gallery = gallery_v10.select_candidate_gallery(remaining_tracks)
            output.append(candidate)

    for candidate in resolved:
        recovered = recovered_by_id.get(str(candidate.id), [])
        if not recovered:
            continue
        _refresh_candidate(candidate)
        metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
        previous_shots = set(metadata.get("track_recovery_shot_ids") or [])
        previous_shots.update(shot_id for shot_id, _score in recovered)
        metadata["track_recovery_shot_ids"] = sorted(previous_shots)
        metadata["track_recovery_count"] = int(metadata.get("track_recovery_count") or 0) + len(recovered)
        metadata["track_recovery_scores"] = {
            shot_id: round(score, 6)
            for shot_id, score in recovered
        }
        metadata["track_recovery_policy"] = (
            "confirmed identity only; >=3 repeated Person-ReID observations; "
            "gallery-shot aggregation; unique winner; cannot-link/face-conflict fail closed"
        )
        candidate.v10_metadata = metadata  # type: ignore[attr-defined]

    output.sort(key=lambda item: (
        0 if str(getattr(item, "identity_status", "UNRESOLVED")).upper() == "RESOLVED" else 1,
        min((track.episode_order for track in getattr(item, "tracks", []) or []), default=999999),
        min((track.shot_ordinal for track in getattr(item, "tracks", []) or []), default=999999),
    ))
    return output


__all__ = ["recover_unresolved_tracks"]
