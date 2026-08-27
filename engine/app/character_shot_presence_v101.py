"""Character V10.1 fragmented Shot-presence recovery.

The global identity classifier is intentionally conservative and the first V10.1
binding pass only recovers one unresolved Track when that Track itself contains enough
repeated observations. Real short-drama footage often fragments a visible person into
several one/two-sample Tracks (close-ups, partial bodies, occlusion, two-person shots).

This second pass keeps identity creation unchanged and answers only:
"is an already-confirmed Character visibly present in this Shot?"

Remaining unresolved Track fragments
-> compare every observation with confirmed identity galleries
-> use Person-ReID as primary evidence, strong high-quality Face as an optional positive
   signal, clothing/body as supporting channels
-> require a unique Character winner per fragment
-> aggregate several fragments across the same Shot
-> enforce same-sample cannot-link / high-quality Face conflict
-> attach only the supported fragments to an existing RESOLVED Character

It never creates a new Character and never weakens the >=3-Shot identity confirmation
contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from engine.app import character_gallery_v10 as gallery_v10
from engine.app.character_identity_v10 import APPEARANCE_SUPPORT, FACE_CONFLICT, FACE_CONFLICT_MIN_SCORE
from engine.app.character_person_features_v9 import feature_channel_scores
from engine.app.character_shot_binding_v101 import _refresh_candidate

RECOVERY_SOURCE = "V10_1_SHOT_FRAGMENT_AGGREGATION"
RECOVERY_POLICY = (
    "confirmed identity only; aggregate short unresolved Track fragments inside one Shot; "
    "Person-ReID primary + optional strong Face + appearance support; unique winner; "
    "cannot-link/face-conflict fail closed"
)

# Match thresholds intentionally reuse the already-validated V10/V9 person/face ranges.
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
FACE_STRONG = 0.52
FACE_POSITIVE_MIN_SCORE = 0.76
WINNER_MARGIN = 0.075

# A non-face recovery must be repeated across the Shot. This is the key difference from
# the existing Track pass: support may come from several short Track fragments.
MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
STRONG_FACE_PRESENCE_SCORE = 0.90
RISKY_CLASSES = {"CONTAMINATED", "PARTIAL"}


@dataclass(frozen=True)
class _ObservationMatch:
    strength: float | None
    strong_face: bool
    hard_conflict: bool


@dataclass(frozen=True)
class _FragmentMatch:
    source_candidate: Any
    track: Any
    target: Any
    score: float
    support_count: int
    support_times: tuple[int, ...]
    strong_face: bool


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


def _observation_match(observation: Any, gallery: list[Any]) -> _ObservationMatch:
    bundle = _bundle(observation)
    if bundle is None:
        return _ObservationMatch(None, False, False)

    by_shot: dict[str, dict[str, float | int | None]] = {}
    for member in gallery:
        if _cannot_link(observation, member):
            return _ObservationMatch(None, False, True)
        member_bundle = _bundle(member)
        if member_bundle is None:
            continue
        scores = feature_channel_scores(bundle, member_bundle)
        if _face_conflict(bundle, member_bundle, scores):
            return _ObservationMatch(None, False, True)

        reid = scores.get("person_reid")
        face = scores.get("face")
        appearance = sum(
            1
            for name in ("clothing_upper", "clothing_lower", "body_hist", "body_structure")
            if scores.get(name) is not None and float(scores[name]) >= APPEARANCE_SUPPORT
        )
        shot_id = str(getattr(member, "shot_id", ""))
        row = by_shot.setdefault(shot_id, {"reid": None, "appearance": 0, "face": None})
        if reid is not None and (row["reid"] is None or float(reid) > float(row["reid"])):
            row["reid"] = float(reid)
            row["appearance"] = int(appearance)
        if (
            face is not None
            and getattr(bundle, "face", None) is not None
            and getattr(member_bundle, "face", None) is not None
            and float(getattr(bundle, "face_score", 0.0) or 0.0) >= FACE_POSITIVE_MIN_SCORE
            and float(getattr(member_bundle, "face_score", 0.0) or 0.0) >= FACE_POSITIVE_MIN_SCORE
            and (row["face"] is None or float(face) > float(row["face"]))
        ):
            row["face"] = float(face)

    reid_rows = sorted(
        [row for row in by_shot.values() if row["reid"] is not None],
        key=lambda row: float(row["reid"]),
        reverse=True,
    )
    face_rows = sorted(
        [float(row["face"]) for row in by_shot.values() if row["face"] is not None],
        reverse=True,
    )

    reid_support: float | None = None
    appearance = 0
    if reid_rows:
        values = [float(row["reid"]) for row in reid_rows[:2]]
        reid_support = float(median(values)) if len(values) >= 2 else values[0]
        appearance = max(int(row["appearance"]) for row in reid_rows[:2])

    face_support: float | None = None
    if face_rows:
        values = face_rows[:2]
        face_support = float(median(values)) if len(values) >= 2 else values[0]

    # Strong Face is allowed as a positive signal only when two independent gallery Shots
    # support it. Face remains optional and is never needed for body/side/back recovery.
    if len(face_rows) >= 2 and face_support is not None and face_support >= FACE_STRONG:
        face_strength = min(0.99, 0.90 + max(0.0, face_support - FACE_STRONG) * 0.15)
        return _ObservationMatch(max(face_strength, reid_support or 0.0), True, False)

    if reid_support is None:
        return _ObservationMatch(None, False, False)

    risky = str(getattr(observation, "instance_class", "") or "").upper() in RISKY_CLASSES
    if reid_support >= REID_STRONG:
        return _ObservationMatch(reid_support, False, False)
    if not risky and reid_support >= REID_SUPPORTED and appearance >= 1:
        return _ObservationMatch(reid_support, False, False)
    if risky and reid_support >= RISKY_REID_SUPPORTED and appearance >= RISKY_APPEARANCE_CHANNELS:
        return _ObservationMatch(reid_support, False, False)
    return _ObservationMatch(None, False, False)


def _fragment_candidate_score(track: Any, gallery: list[Any]) -> tuple[float, int, tuple[int, ...], bool] | None:
    strengths: list[float] = []
    support_times: set[int] = set()
    strong_face = False
    for observation in list(getattr(track, "observations", []) or []):
        match = _observation_match(observation, gallery)
        if match.hard_conflict:
            return None
        if match.strength is None:
            continue
        strengths.append(float(match.strength))
        support_times.add(int(getattr(observation, "source_time_us", 0)))
        strong_face = strong_face or match.strong_face
    if not strengths:
        return None
    ordered = sorted(strengths, reverse=True)
    score = float(median(ordered[: min(3, len(ordered))]))
    return score, len(strengths), tuple(sorted(support_times)), strong_face


def _best_fragment_target(track: Any, resolved: list[Any]) -> tuple[Any | None, tuple[float, int, tuple[int, ...], bool] | None]:
    scored: list[tuple[float, Any, tuple[float, int, tuple[int, ...], bool]]] = []
    for candidate in resolved:
        gallery = _gallery_observations(candidate)
        if not gallery:
            continue
        summary = _fragment_candidate_score(track, gallery)
        if summary is not None:
            scored.append((summary[0], candidate, summary))
    if not scored:
        return None, None
    scored.sort(key=lambda row: row[0], reverse=True)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < WINNER_MARGIN:
        return None, None
    return scored[0][1], scored[0][2]


def _tracks_cannot_link(left: Any, right: Any) -> bool:
    for left_observation in list(getattr(left, "observations", []) or []):
        for right_observation in list(getattr(right, "observations", []) or []):
            if _cannot_link(left_observation, right_observation):
                return True
    return False


def _non_conflicting_fragments(items: list[_FragmentMatch]) -> list[_FragmentMatch]:
    """Keep the strongest mutually-compatible fragments for one Character in one Shot."""

    selected: list[_FragmentMatch] = []
    for item in sorted(items, key=lambda value: value.score, reverse=True):
        if any(_tracks_cannot_link(item.track, existing.track) for existing in selected):
            continue
        selected.append(item)
    return selected


def _group_is_recoverable(items: list[_FragmentMatch]) -> bool:
    if not items:
        return False
    if any(item.strong_face and item.score >= STRONG_FACE_PRESENCE_SCORE for item in items):
        return True
    support_count = sum(item.support_count for item in items)
    support_times = {value for item in items for value in item.support_times}
    if support_count < MIN_SHOT_SUPPORT_OBSERVATIONS or len(support_times) < MIN_SHOT_SUPPORT_TIMESTAMPS:
        return False
    values = sorted((item.score for item in items), reverse=True)
    return float(median(values[: min(5, len(values))])) >= MIN_SHOT_MEDIAN


def _mark_fragment_recovered(track: Any, target: Any, score: float, *, support_count: int, strong_face: bool) -> None:
    track.identity_recovery = {  # type: ignore[attr-defined]
        "source": RECOVERY_SOURCE,
        "target_candidate_id": str(getattr(target, "id", "")),
        "shot_id": str(getattr(track, "shot_id", "")),
        "score": round(float(score), 6),
        "observation_count": len(list(getattr(track, "observations", []) or [])),
        "support_count": int(support_count),
        "strong_face_support": bool(strong_face),
        "policy": RECOVERY_POLICY,
    }


def recover_fragmented_shot_presence(candidates: list[Any]) -> list[Any]:
    """Recover known Character presence from several short unresolved Track fragments."""

    resolved = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "identity_status", "UNRESOLVED")).upper() == "RESOLVED"
    ]
    unresolved = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "identity_status", "UNRESOLVED")).upper() != "RESOLVED"
    ]
    if not resolved or not unresolved:
        return candidates

    groups: dict[tuple[str, str], list[_FragmentMatch]] = {}
    target_by_id = {str(candidate.id): candidate for candidate in resolved}
    for source_candidate in unresolved:
        for track in list(getattr(source_candidate, "tracks", []) or []):
            target, summary = _best_fragment_target(track, resolved)
            if target is None or summary is None:
                continue
            score, support_count, support_times, strong_face = summary
            item = _FragmentMatch(
                source_candidate=source_candidate,
                track=track,
                target=target,
                score=float(score),
                support_count=int(support_count),
                support_times=tuple(support_times),
                strong_face=bool(strong_face),
            )
            groups.setdefault((str(track.shot_id), str(target.id)), []).append(item)

    recovered_by_id: dict[str, list[_FragmentMatch]] = {}
    for (_shot_id, target_id), raw_items in groups.items():
        items = _non_conflicting_fragments(raw_items)
        if not _group_is_recoverable(items):
            continue
        target = target_by_id[target_id]
        for item in items:
            source_tracks = list(getattr(item.source_candidate, "tracks", []) or [])
            if item.track not in source_tracks:
                continue
            _mark_fragment_recovered(
                item.track,
                target,
                item.score,
                support_count=item.support_count,
                strong_face=item.strong_face,
            )
            target.tracks.append(item.track)
            item.source_candidate.tracks = [track for track in source_tracks if track is not item.track]
            recovered_by_id.setdefault(target_id, []).append(item)

    output: list[Any] = list(resolved)
    for candidate in unresolved:
        remaining_tracks = list(getattr(candidate, "tracks", []) or [])
        if not remaining_tracks:
            continue
        candidate.gallery = gallery_v10.select_candidate_gallery(remaining_tracks)
        output.append(candidate)

    for candidate in resolved:
        recovered = recovered_by_id.get(str(candidate.id), [])
        if not recovered:
            continue
        _refresh_candidate(candidate)
        metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
        previous_shots = set(metadata.get("track_recovery_shot_ids") or [])
        previous_shots.update(str(item.track.shot_id) for item in recovered)
        metadata["track_recovery_shot_ids"] = sorted(previous_shots)
        metadata["track_recovery_count"] = int(metadata.get("track_recovery_count") or 0) + len(recovered)
        previous_scores = dict(metadata.get("track_recovery_scores") or {})
        for item in recovered:
            shot_id = str(item.track.shot_id)
            previous_scores[shot_id] = round(max(float(previous_scores.get(shot_id) or 0.0), item.score), 6)
        metadata["track_recovery_scores"] = previous_scores
        sources = set(metadata.get("track_recovery_sources") or [])
        existing_source = metadata.get("track_recovery_source")
        if existing_source:
            sources.add(str(existing_source))
        sources.add(RECOVERY_SOURCE)
        metadata["track_recovery_sources"] = sorted(sources)
        metadata["track_recovery_source"] = RECOVERY_SOURCE if len(sources) == 1 else "MULTI_SOURCE"
        metadata["shot_fragment_recovery_count"] = int(metadata.get("shot_fragment_recovery_count") or 0) + len(recovered)
        metadata["shot_fragment_recovery_policy"] = RECOVERY_POLICY
        candidate.v10_metadata = metadata  # type: ignore[attr-defined]

    output.sort(key=lambda item: (
        0 if str(getattr(item, "identity_status", "UNRESOLVED")).upper() == "RESOLVED" else 1,
        min((track.episode_order for track in getattr(item, "tracks", []) or []), default=999999),
        min((track.shot_ordinal for track in getattr(item, "tracks", []) or []), default=999999),
    ))
    return output


__all__ = ["RECOVERY_SOURCE", "recover_fragmented_shot_presence"]
