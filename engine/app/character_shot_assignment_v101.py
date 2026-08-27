"""Character V10.1 explicit Shot -> Character assignment engine.

Global identity and Shot presence are deliberately different decisions:

1. ``resolve_global_identities`` decides which project-level Characters exist.
2. This module independently decides which already-confirmed Characters are present in
   each Shot, using every original Track/Observation from that Shot.
3. Final Asset materialization consumes the explicit assignment metadata instead of
   inferring bindings from ``candidate.tracks``.

The engine never creates a Character and never mutates Track ownership.  A Track may
remain UNRESOLVED evidence while the Shot-level aggregate is still strong enough to say
that a known Character is present.  This is important for close-ups, two-person shots,
partial bodies and MOT fragmentation.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from engine.app import character_gallery_v10 as gallery_v10
from engine.app.character_identity_v10 import APPEARANCE_SUPPORT, FACE_CONFLICT
from engine.app.character_person_features_v9 import feature_channel_scores

ASSIGNMENT_VERSION = "v10.1-shot-character-assignment-1"
ASSIGNMENT_SOURCE = "V10_1_SHOT_CHARACTER_ASSIGNMENT"
ASSIGNMENT_POLICY = (
    "confirmed identities first; independently score every Shot against known Character galleries; "
    "Face/ReID/appearance temporal aggregation; current-Shot cannot-link constraints; unique winner; "
    "never create identity and never move Track ownership"
)

# SFace is only a known-identity Shot-presence signal here.  A single strong face must
# agree with >=2 independent gallery Shots; a weaker face must repeat in the current Shot.
FACE_PAIR_MIN_SCORE = 0.72
FACE_SUPPORTED = 0.36
FACE_STRONG = 0.50
FACE_WINNER_MARGIN = 0.08
MIN_FACE_REPEAT_OBSERVATIONS = 2
MIN_FACE_REPEAT_TIMESTAMPS = 2
MIN_FACE_REPEAT_MEDIAN = 0.40

# Body/ReID remains the primary non-face presence path and must repeat over time.
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
REID_WINNER_MARGIN = 0.07
MIN_BODY_SUPPORT_OBSERVATIONS = 3
MIN_BODY_SUPPORT_TIMESTAMPS = 3
MIN_BODY_MEDIAN = 0.76
RISKY_CLASSES = {"CONTAMINATED", "PARTIAL"}


@dataclass(frozen=True)
class _TrackFragment:
    source_track: Any
    observations: tuple[Any, ...]

    @property
    def shot_id(self) -> str:
        return str(getattr(self.source_track, "shot_id", ""))

    @property
    def shot_ordinal(self) -> int:
        return int(getattr(self.source_track, "shot_ordinal", 0) or 0)

    @property
    def episode_order(self) -> int:
        return int(getattr(self.source_track, "episode_order", 0) or 0)


@dataclass(frozen=True)
class _CandidateScore:
    candidate: Any
    face_similarity: float | None
    face_confidence: float | None
    face_support_count: int
    face_support_times: tuple[int, ...]
    strong_face: bool
    reid_similarity: float | None
    reid_confidence: float | None
    reid_support_count: int
    reid_support_times: tuple[int, ...]
    hard_conflict: bool


@dataclass(frozen=True)
class _FragmentVote:
    fragment: _TrackFragment
    target: Any
    mode: str
    confidence: float
    winner_margin: float
    face_similarity: float | None
    face_support_count: int
    face_support_times: tuple[int, ...]
    reid_similarity: float | None
    reid_support_count: int
    reid_support_times: tuple[int, ...]


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
    if value is None:
        return None
    if getattr(value, "person_reid", None) is None and getattr(value, "face", None) is None:
        return None
    return value


def _gallery_observations(candidate: Any) -> list[Any]:
    representatives = list(getattr(candidate, "gallery", []) or [])
    if not representatives:
        representatives = gallery_v10.select_candidate_gallery(list(getattr(candidate, "tracks", []) or []))
    return [
        representative.observation
        for representative in representatives
        if _bundle(getattr(representative, "observation", None)) is not None
    ]


def _face_presence_confidence(similarity: float) -> float:
    # SFace cosine values are not calibrated probabilities.  Map the known-person
    # threshold band into a conservative Shot-presence confidence band for UI/Final.
    return min(0.98, 0.84 + max(0.0, similarity - FACE_SUPPORTED) * 0.35)


def _observation_candidate_channels(observation: Any, gallery: list[Any]) -> tuple[
    float | None,
    int,
    float | None,
    int,
    bool,
]:
    """Return (face, face_gallery_shots, reid, appearance_support, hard_conflict)."""

    bundle = _bundle(observation)
    if bundle is None:
        return None, 0, None, 0, False

    by_shot: dict[str, dict[str, float | int | None]] = {}
    for member in gallery:
        if _cannot_link(observation, member):
            return None, 0, None, 0, True
        member_bundle = _bundle(member)
        if member_bundle is None:
            continue
        scores = feature_channel_scores(bundle, member_bundle)
        shot_id = str(getattr(member, "shot_id", ""))
        row = by_shot.setdefault(shot_id, {"face": None, "reid": None, "appearance": 0})

        reid = scores.get("person_reid")
        if reid is not None and (row["reid"] is None or float(reid) > float(row["reid"])):
            row["reid"] = float(reid)
            row["appearance"] = sum(
                1
                for name in ("clothing_upper", "clothing_lower", "body_hist", "body_structure")
                if scores.get(name) is not None and float(scores[name]) >= APPEARANCE_SUPPORT
            )

        face = scores.get("face")
        if (
            face is not None
            and getattr(bundle, "face", None) is not None
            and getattr(member_bundle, "face", None) is not None
            and float(getattr(bundle, "face_score", 0.0) or 0.0) >= FACE_PAIR_MIN_SCORE
            and float(getattr(member_bundle, "face_score", 0.0) or 0.0) >= FACE_PAIR_MIN_SCORE
            and (row["face"] is None or float(face) > float(row["face"]))
        ):
            row["face"] = float(face)

    face_rows = sorted(
        [float(row["face"]) for row in by_shot.values() if row["face"] is not None],
        reverse=True,
    )
    reid_rows = sorted(
        [row for row in by_shot.values() if row["reid"] is not None],
        key=lambda row: float(row["reid"]),
        reverse=True,
    )

    # High-quality Face conflict is fail-closed only when it is consistent across two
    # independent gallery Shots.  One noisy/profile gallery crop is not enough to veto.
    if len(face_rows) >= 2:
        conflicts = [value for value in face_rows if value <= FACE_CONFLICT]
        positives = [value for value in face_rows if value >= FACE_SUPPORTED]
        if len(conflicts) >= 2 and not positives:
            return None, len(face_rows), None, 0, True

    face_similarity: float | None = None
    if len(face_rows) >= 2:
        face_similarity = float(median(face_rows[:2]))

    reid_similarity: float | None = None
    appearance = 0
    if reid_rows:
        values = [float(row["reid"]) for row in reid_rows[:2]]
        reid_similarity = float(median(values)) if len(values) >= 2 else values[0]
        appearance = max(int(row["appearance"]) for row in reid_rows[:2])

    return face_similarity, len(face_rows), reid_similarity, appearance, False


def _score_fragment_for_candidate(fragment: _TrackFragment, candidate: Any) -> _CandidateScore | None:
    gallery = _gallery_observations(candidate)
    if not gallery:
        return None

    face_values: list[float] = []
    face_times: set[int] = set()
    reid_values: list[float] = []
    reid_times: set[int] = set()

    for observation in fragment.observations:
        face, face_gallery_shots, reid, appearance, hard_conflict = _observation_candidate_channels(observation, gallery)
        if hard_conflict:
            return _CandidateScore(candidate, None, None, 0, (), False, None, None, 0, (), True)
        source_time_us = int(getattr(observation, "source_time_us", 0) or 0)

        if face_gallery_shots >= 2 and face is not None and face >= FACE_SUPPORTED:
            face_values.append(float(face))
            face_times.add(source_time_us)

        if reid is not None:
            risky = str(getattr(observation, "instance_class", "") or "").upper() in RISKY_CLASSES
            accepted = (
                reid >= REID_STRONG
                or (not risky and reid >= REID_SUPPORTED and appearance >= 1)
                or (risky and reid >= RISKY_REID_SUPPORTED and appearance >= RISKY_APPEARANCE_CHANNELS)
            )
            if accepted:
                reid_values.append(float(reid))
                reid_times.add(source_time_us)

    if not face_values and not reid_values:
        return None

    face_similarity = float(median(sorted(face_values, reverse=True)[:3])) if face_values else None
    reid_similarity = float(median(sorted(reid_values, reverse=True)[:3])) if reid_values else None
    return _CandidateScore(
        candidate=candidate,
        face_similarity=face_similarity,
        face_confidence=_face_presence_confidence(face_similarity) if face_similarity is not None else None,
        face_support_count=len(face_values),
        face_support_times=tuple(sorted(face_times)),
        strong_face=bool(face_values and max(face_values) >= FACE_STRONG),
        reid_similarity=reid_similarity,
        reid_confidence=reid_similarity,
        reid_support_count=len(reid_values),
        reid_support_times=tuple(sorted(reid_times)),
        hard_conflict=False,
    )


def _tracks_cannot_link(left_observations: tuple[Any, ...], right_track: Any) -> bool:
    for left in left_observations:
        for right in list(getattr(right_track, "observations", []) or []):
            if _cannot_link(left, right):
                return True
    return False


def _fragment_conflicts_with_direct_identity(
    fragment: _TrackFragment,
    candidate: Any,
    direct_tracks: dict[tuple[str, str], list[Any]],
) -> bool:
    key = (fragment.shot_id, str(getattr(candidate, "id", "")))
    return any(_tracks_cannot_link(fragment.observations, track) for track in direct_tracks.get(key, []))


def _best_fragment_vote(
    fragment: _TrackFragment,
    resolved: list[Any],
    direct_tracks: dict[tuple[str, str], list[Any]],
) -> _FragmentVote | None:
    scored: list[_CandidateScore] = []
    for candidate in resolved:
        if _fragment_conflicts_with_direct_identity(fragment, candidate, direct_tracks):
            continue
        value = _score_fragment_for_candidate(fragment, candidate)
        if value is not None and not value.hard_conflict:
            scored.append(value)
    if not scored:
        return None

    # Face is preferred whenever it has supported evidence.  This prevents a synthetic
    # body box around a close-up face from overriding the actual SFace identity.
    face_scored = [item for item in scored if item.face_similarity is not None]
    if face_scored:
        ranked = sorted(face_scored, key=lambda item: float(item.face_similarity or -1.0), reverse=True)
        best = ranked[0]
        margin = (
            float(best.face_similarity or 0.0) - float(ranked[1].face_similarity or 0.0)
            if len(ranked) > 1 else 1.0
        )
        if len(ranked) > 1 and margin < FACE_WINNER_MARGIN:
            return None
        return _FragmentVote(
            fragment=fragment,
            target=best.candidate,
            mode="FACE",
            confidence=float(best.face_confidence or 0.0),
            winner_margin=margin,
            face_similarity=best.face_similarity,
            face_support_count=best.face_support_count,
            face_support_times=best.face_support_times,
            reid_similarity=best.reid_similarity,
            reid_support_count=best.reid_support_count,
            reid_support_times=best.reid_support_times,
        )

    body_scored = [item for item in scored if item.reid_similarity is not None]
    if not body_scored:
        return None
    ranked = sorted(body_scored, key=lambda item: float(item.reid_similarity or -1.0), reverse=True)
    best = ranked[0]
    margin = (
        float(best.reid_similarity or 0.0) - float(ranked[1].reid_similarity or 0.0)
        if len(ranked) > 1 else 1.0
    )
    if len(ranked) > 1 and margin < REID_WINNER_MARGIN:
        return None
    return _FragmentVote(
        fragment=fragment,
        target=best.candidate,
        mode="BODY_REID",
        confidence=float(best.reid_confidence or 0.0),
        winner_margin=margin,
        face_similarity=None,
        face_support_count=0,
        face_support_times=(),
        reid_similarity=best.reid_similarity,
        reid_support_count=best.reid_support_count,
        reid_support_times=best.reid_support_times,
    )


def _fragments_cannot_link(left: _TrackFragment, right: _TrackFragment) -> bool:
    for left_observation in left.observations:
        for right_observation in right.observations:
            if _cannot_link(left_observation, right_observation):
                return True
    return False


def _compatible_votes(items: list[_FragmentVote]) -> list[_FragmentVote]:
    """One Character cannot occupy two cannot-link Person Instances at the same time."""

    selected: list[_FragmentVote] = []
    for item in sorted(items, key=lambda value: value.confidence, reverse=True):
        if any(_fragments_cannot_link(item.fragment, existing.fragment) for existing in selected):
            continue
        selected.append(item)
    return selected


def _group_mode(items: list[_FragmentVote]) -> str | None:
    face_items = [item for item in items if item.face_similarity is not None]
    if any(float(item.face_similarity or 0.0) >= FACE_STRONG for item in face_items):
        return "FACE_STRONG"

    face_count = sum(item.face_support_count for item in face_items)
    face_times = {value for item in face_items for value in item.face_support_times}
    face_values = [float(item.face_similarity) for item in face_items if item.face_similarity is not None]
    if (
        face_count >= MIN_FACE_REPEAT_OBSERVATIONS
        and len(face_times) >= MIN_FACE_REPEAT_TIMESTAMPS
        and face_values
        and float(median(sorted(face_values, reverse=True)[:5])) >= MIN_FACE_REPEAT_MEDIAN
    ):
        return "FACE_REPEATED"

    body_items = [item for item in items if item.reid_similarity is not None]
    body_count = sum(item.reid_support_count for item in body_items)
    body_times = {value for item in body_items for value in item.reid_support_times}
    body_values = [float(item.reid_similarity) for item in body_items if item.reid_similarity is not None]
    if (
        body_count >= MIN_BODY_SUPPORT_OBSERVATIONS
        and len(body_times) >= MIN_BODY_SUPPORT_TIMESTAMPS
        and body_values
        and float(median(sorted(body_values, reverse=True)[:5])) >= MIN_BODY_MEDIAN
    ):
        return "BODY_REID"
    return None


def _identity_confidence(candidate: Any) -> float:
    values = [float(value) for value in (getattr(candidate, "scores", []) or []) if 0.0 <= float(value) <= 1.0]
    if not values:
        return 0.90
    return max(0.0, min(1.0, float(median(sorted(values, reverse=True)[:4]))))


def _direct_assignments(resolved: list[Any]) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[tuple[str, str], list[Any]],
    set[int],
]:
    assignments: dict[str, list[dict[str, Any]]] = {str(candidate.id): [] for candidate in resolved}
    direct_tracks: dict[tuple[str, str], list[Any]] = {}
    direct_observation_ids: set[int] = set()

    for candidate in resolved:
        candidate_id = str(candidate.id)
        by_shot: dict[str, list[Any]] = {}
        for track in list(getattr(candidate, "tracks", []) or []):
            by_shot.setdefault(str(track.shot_id), []).append(track)
            direct_observation_ids.update(id(observation) for observation in list(getattr(track, "observations", []) or []))
        for shot_id, tracks in by_shot.items():
            direct_tracks[(shot_id, candidate_id)] = list(tracks)
            observations = [observation for track in tracks for observation in list(getattr(track, "observations", []) or [])]
            first_track = tracks[0]
            assignments[candidate_id].append({
                "shot_id": shot_id,
                "shot_ordinal": int(getattr(first_track, "shot_ordinal", 0) or 0),
                "episode_order": int(getattr(first_track, "episode_order", 0) or 0),
                "confidence": round(_identity_confidence(candidate), 6),
                "mode": "DIRECT_IDENTITY",
                "source": ASSIGNMENT_SOURCE,
                "support_count": len(observations),
                "support_timestamp_count": len({int(getattr(item, "source_time_us", 0) or 0) for item in observations}),
                "track_count": len(tracks),
                "face_support_count": sum(1 for item in observations if bool(getattr(item, "face_visible", False))),
                "winner_margin": None,
            })
    return assignments, direct_tracks, direct_observation_ids


def _unassigned_fragments(tracks: list[Any], direct_observation_ids: set[int]) -> list[_TrackFragment]:
    result: list[_TrackFragment] = []
    for track in tracks:
        observations = tuple(
            observation
            for observation in list(getattr(track, "observations", []) or [])
            if id(observation) not in direct_observation_ids and _bundle(observation) is not None
        )
        if observations:
            result.append(_TrackFragment(source_track=track, observations=observations))
    return result


def assign_shot_characters(tracks: list[Any], candidates: list[Any]) -> list[Any]:
    """Attach explicit Shot-presence metadata to each RESOLVED identity.

    ``candidate.tracks`` remains untouched.  This makes Final binding a first-class
    Shot-level decision rather than a side effect of Track ownership.
    """

    resolved = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "identity_status", "UNRESOLVED")).upper() == "RESOLVED"
    ]
    if not resolved:
        return candidates

    assignments_by_candidate, direct_tracks, direct_observation_ids = _direct_assignments(resolved)
    groups: dict[tuple[str, str], list[_FragmentVote]] = {}

    for fragment in _unassigned_fragments(tracks, direct_observation_ids):
        vote = _best_fragment_vote(fragment, resolved, direct_tracks)
        if vote is None:
            continue
        groups.setdefault((fragment.shot_id, str(vote.target.id)), []).append(vote)

    for (shot_id, candidate_id), raw_votes in groups.items():
        if any(item["shot_id"] == shot_id for item in assignments_by_candidate.get(candidate_id, [])):
            continue
        votes = _compatible_votes(raw_votes)
        mode = _group_mode(votes)
        if mode is None:
            continue

        first = votes[0].fragment
        face_items = [item for item in votes if item.face_similarity is not None]
        body_items = [item for item in votes if item.reid_similarity is not None]
        if mode.startswith("FACE"):
            confidence_values = [item.confidence for item in face_items]
        else:
            confidence_values = [item.confidence for item in body_items]
        confidence = max(confidence_values) if mode == "FACE_STRONG" else float(
            median(sorted(confidence_values, reverse=True)[:5])
        )

        support_times = {
            value
            for item in votes
            for value in (*item.face_support_times, *item.reid_support_times)
        }
        assignments_by_candidate.setdefault(candidate_id, []).append({
            "shot_id": shot_id,
            "shot_ordinal": first.shot_ordinal,
            "episode_order": first.episode_order,
            "confidence": round(max(0.0, min(1.0, confidence)), 6),
            "mode": mode,
            "source": ASSIGNMENT_SOURCE,
            "support_count": sum(max(item.face_support_count, item.reid_support_count) for item in votes),
            "support_timestamp_count": len(support_times),
            "track_count": len(votes),
            "face_support_count": sum(item.face_support_count for item in votes),
            "winner_margin": round(min(item.winner_margin for item in votes), 6),
        })

    for candidate in resolved:
        values = assignments_by_candidate.get(str(candidate.id), [])
        values.sort(key=lambda item: (
            int(item.get("episode_order") or 0),
            int(item.get("shot_ordinal") or 0),
            str(item.get("shot_id") or ""),
        ))
        metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
        metadata["shot_assignment_version"] = ASSIGNMENT_VERSION
        metadata["shot_assignment_source"] = ASSIGNMENT_SOURCE
        metadata["shot_assignment_policy"] = ASSIGNMENT_POLICY
        metadata["shot_presence_assignments"] = values
        metadata["shot_presence_shot_ids"] = [str(item["shot_id"]) for item in values]
        metadata["shot_presence_count"] = len(values)
        metadata["shot_presence_recovered_count"] = sum(
            1 for item in values if str(item.get("mode")) != "DIRECT_IDENTITY"
        )
        candidate.v10_metadata = metadata  # type: ignore[attr-defined]

    return candidates


__all__ = [
    "ASSIGNMENT_VERSION",
    "ASSIGNMENT_SOURCE",
    "ASSIGNMENT_POLICY",
    "assign_shot_characters",
]
