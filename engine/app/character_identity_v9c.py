"""Character V9 Phase C: Person Gallery Anchor-first identity resolver.

Formal identity contract:
- identity input is CLEAN Person Image evidence, never a whole frame and never a Track id;
- Person ReID / clothing / body / optional face stay separate and decisions are explainable;
- first confirm one stable multi-shot Person Gallery, then every remaining image must compare
  with all confirmed galleries before a new Character may be created;
- MATCH -> absorb; AMBIGUOUS -> UNRESOLVED; only CLEARLY DIFFERENT evidence may seed a new gallery;
- same-sample spatial cannot-link is a hard negative constraint;
- partial / occluded / contaminated observations may attach to an existing confirmed gallery
  conservatively, but can never create a Character.

No inferred demographic attribute is used for visual identity. User-supplied metadata may be stored
later on Final Assets, but visual identity itself uses observable person appearance only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

from engine.app import character_gallery_v9 as gallery_v9
from engine.app import character_visual_v5 as v5
from engine.app.character_person_features_v9 import PersonFeatureBundle, feature_channel_scores
from engine.app.studio_v2 import new_id

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft
Observation = v5.Observation
DecisionStatus = Literal["MATCH", "AMBIGUOUS", "DIFFERENT"]

# A new Character needs a stable group of clean person images from independent Shots.
CONFIRM_MIN_SHOTS = 3
CONFIRM_MIN_IMAGES = 3
SEED_MIN_QUALITY = 0.62
CONFIRM_MEDIAN_STRENGTH = 0.70
GALLERY_LIMIT = 24

# Multi-channel match thresholds. No single positive channel is sufficient by itself.
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
REID_AMBIGUOUS = 0.62
FACE_STRONG = 0.52
FACE_SUPPORTED = 0.38
FACE_HARD_CONFLICT = 0.18
FACE_HARD_CONFLICT_MIN_SCORE = 0.76
CLOTHING_STRONG = 0.84
CLOTHING_SUPPORTED = 0.72
CLOTHING_AMBIGUOUS = 0.64
BODY_HIST_SUPPORTED = 0.76
BODY_STRUCTURE_SUPPORTED = 0.68

# Existing confirmed galleries are intentionally easier to absorb into than it is to create a
# brand-new identity. This asymmetry prevents A -> A2 fragmentation.
GALLERY_MATCH_MIN_SHOTS = 2
GALLERY_SINGLE_MATCH_EXCEPTION = 0.90
AMBIGUITY_MARGIN = 0.075

# Dirty / partial evidence may only extend an existing identity with stronger multi-shot support.
EXTENSION_REID_STRONG = 0.89
EXTENSION_APPEARANCE_SUPPORTED = 0.76
EXTENSION_MIN_GALLERY_SHOTS = 2


@dataclass(frozen=True)
class PersonEvidence:
    index: int
    track_index: int
    observation: Observation
    bundle: PersonFeatureBundle
    quality: float

    @property
    def shot_id(self) -> str:
        return str(self.observation.shot_id)

    @property
    def source_time_us(self) -> int:
        return int(self.observation.source_time_us)


@dataclass(frozen=True)
class PairDecision:
    status: DecisionStatus
    strength: float
    channels: dict[str, float | None]
    reasons: tuple[str, ...]
    hard_conflict: bool = False


@dataclass
class ConfirmedGallery:
    ordinal: int
    evidence_indices: set[int] = field(default_factory=set)
    strengths: list[float] = field(default_factory=list)
    seed_index: int | None = None


def _score(value: float | None) -> float:
    return float(value) if value is not None else -1.0


def _positive(value: float | None) -> float:
    return max(0.0, float(value)) if value is not None else 0.0


def _bundle(observation: Observation) -> PersonFeatureBundle | None:
    value = getattr(observation, "person_feature_bundle", None)
    return value if isinstance(value, PersonFeatureBundle) else None


def _is_clean(observation: Observation) -> bool:
    return bool(
        str(getattr(observation, "instance_class", "")) == "CLEAN"
        and bool(getattr(observation, "gallery_eligible", False))
    )


def _instance_id(observation: Observation) -> str | None:
    value = getattr(observation, "instance_id", None)
    return str(value) if value else None


def _cannot_link(left: Observation, right: Observation) -> bool:
    left_id = _instance_id(left)
    right_id = _instance_id(right)
    if left_id and right_id:
        left_links = {str(item) for item in (getattr(left, "cannot_link_instance_ids", []) or [])}
        right_links = {str(item) for item in (getattr(right, "cannot_link_instance_ids", []) or [])}
        if right_id in left_links or left_id in right_links:
            return True

    # Compatibility fallback for synthetic tests / older Evidence without instance ids.
    if (
        left.shot_id == right.shot_id
        and abs(int(left.source_time_us) - int(right.source_time_us)) <= 45_000
        and v5.bbox_iou(left.bbox, right.bbox) < 0.35
    ):
        return True
    return False


def _face_hard_conflict(left: PersonFeatureBundle, right: PersonFeatureBundle, scores: dict[str, float | None]) -> bool:
    face = scores.get("face")
    return bool(
        left.face is not None
        and right.face is not None
        and left.face_score >= FACE_HARD_CONFLICT_MIN_SCORE
        and right.face_score >= FACE_HARD_CONFLICT_MIN_SCORE
        and face is not None
        and face <= FACE_HARD_CONFLICT
    )


def _appearance_support(scores: dict[str, float | None], threshold: float) -> int:
    return sum(
        1
        for name in ("clothing_upper", "clothing_lower", "body_hist", "body_structure")
        if scores.get(name) is not None and float(scores[name]) >= threshold
    )


def _decision_strength(scores: dict[str, float | None]) -> float:
    """Explainable ranking score only; identity is never represented by this number or one vector."""

    weighted: list[tuple[float, float]] = []
    for name, weight in (
        ("person_reid", 0.36),
        ("clothing_upper", 0.16),
        ("clothing_lower", 0.14),
        ("body_hist", 0.10),
        ("body_structure", 0.08),
        ("face", 0.16),
    ):
        value = scores.get(name)
        if value is not None:
            weighted.append((max(0.0, min(1.0, float(value))), weight))
    denominator = sum(weight for _value, weight in weighted)
    if denominator <= 1e-9:
        return 0.0
    return sum(value * weight for value, weight in weighted) / denominator


def compare_person_images(left: PersonEvidence, right: PersonEvidence) -> PairDecision:
    if _cannot_link(left.observation, right.observation):
        return PairDecision("DIFFERENT", 1.0, {}, ("same-sample-cannot-link",), True)

    scores = feature_channel_scores(left.bundle, right.bundle)
    strength = _decision_strength(scores)
    reasons: list[str] = []

    if _face_hard_conflict(left.bundle, right.bundle, scores):
        return PairDecision("DIFFERENT", max(strength, 0.85), scores, ("high-quality-face-conflict",), True)

    reid = _score(scores.get("person_reid"))
    face = _score(scores.get("face"))
    upper = _score(scores.get("clothing_upper"))
    lower = _score(scores.get("clothing_lower"))
    body_hist = _score(scores.get("body_hist"))
    body_structure = _score(scores.get("body_structure"))

    appearance_supported = sum(
        int(value >= threshold)
        for value, threshold in (
            (upper, CLOTHING_SUPPORTED),
            (lower, CLOTHING_SUPPORTED),
            (body_hist, BODY_HIST_SUPPORTED),
            (body_structure, BODY_STRUCTURE_SUPPORTED),
        )
    )
    clothing_strong = int(upper >= CLOTHING_STRONG) + int(lower >= CLOTHING_STRONG)

    # Positive identity needs at least two independent channels.
    if reid >= REID_STRONG and (appearance_supported >= 1 or face >= FACE_SUPPORTED):
        reasons.extend(("reid-strong", "second-channel-support"))
        return PairDecision("MATCH", strength, scores, tuple(reasons))
    if reid >= REID_SUPPORTED and face >= FACE_STRONG and appearance_supported >= 1:
        reasons.extend(("reid-supported", "face-strong", "appearance-support"))
        return PairDecision("MATCH", strength, scores, tuple(reasons))
    if reid >= REID_SUPPORTED and clothing_strong >= 2:
        reasons.extend(("reid-supported", "upper-lower-clothing-strong"))
        return PairDecision("MATCH", strength, scores, tuple(reasons))

    # Similar but not sufficiently proven -> unresolved, never a new Character seed against a known gallery.
    ambiguous = bool(
        reid >= REID_AMBIGUOUS
        or face >= FACE_SUPPORTED
        or (upper >= CLOTHING_AMBIGUOUS and lower >= CLOTHING_AMBIGUOUS)
        or (reid >= 0.56 and appearance_supported >= 1)
    )
    if ambiguous:
        if reid >= REID_AMBIGUOUS:
            reasons.append("reid-ambiguous")
        if face >= FACE_SUPPORTED:
            reasons.append("face-support-without-person-proof")
        if upper >= CLOTHING_AMBIGUOUS and lower >= CLOTHING_AMBIGUOUS:
            reasons.append("clothing-similar")
        return PairDecision("AMBIGUOUS", strength, scores, tuple(reasons or ["insufficient-multichannel-proof"]))

    return PairDecision("DIFFERENT", 1.0 - min(1.0, strength), scores, ("no-multichannel-match",))


def _clean_evidence(tracks: list[TrackDraft]) -> list[PersonEvidence]:
    result: list[PersonEvidence] = []
    for track_index, track in enumerate(tracks):
        # Tracking V9 already selects CLEAN representatives; recalc defensively for compatibility.
        representatives = gallery_v9.select_track_representatives(track)
        track.representatives = representatives
        for representative in representatives:
            observation = representative.observation
            bundle = _bundle(observation)
            if not representative.clean or not _is_clean(observation) or bundle is None:
                continue
            if bundle.person_reid is None:
                # A clean image with no body ReID can remain Evidence, but cannot seed an automatic identity.
                continue
            result.append(PersonEvidence(
                index=len(result),
                track_index=track_index,
                observation=observation,
                bundle=bundle,
                quality=max(float(representative.quality_score), float(bundle.quality)),
            ))
    return result


def _gallery_members(identity: ConfirmedGallery, evidence: list[PersonEvidence]) -> list[PersonEvidence]:
    values = [evidence[index] for index in identity.evidence_indices]
    # Keep at most two high-quality images per Shot; preserve cross-shot evidence.
    by_shot: dict[str, list[PersonEvidence]] = {}
    for item in sorted(values, key=lambda value: value.quality, reverse=True):
        bucket = by_shot.setdefault(item.shot_id, [])
        if len(bucket) < 2:
            bucket.append(item)
    result = [item for bucket in by_shot.values() for item in bucket]
    result.sort(key=lambda value: value.quality, reverse=True)
    return result[:GALLERY_LIMIT]


def _gallery_decision(
    item: PersonEvidence,
    identity: ConfirmedGallery,
    evidence: list[PersonEvidence],
    *,
    strict_extension: bool = False,
) -> PairDecision:
    members = _gallery_members(identity, evidence)
    decisions = [compare_person_images(item, member) for member in members]
    hard = [decision for decision in decisions if decision.hard_conflict]
    if hard:
        return PairDecision("DIFFERENT", 1.0, hard[0].channels, hard[0].reasons, True)

    matches = [decision for decision in decisions if decision.status == "MATCH"]
    ambiguous = [decision for decision in decisions if decision.status == "AMBIGUOUS"]
    if matches:
        matched_shots = {
            member.shot_id
            for member, decision in zip(members, decisions)
            if decision.status == "MATCH"
        }
        best = max(matches, key=lambda decision: decision.strength)
        required = EXTENSION_MIN_GALLERY_SHOTS if strict_extension else GALLERY_MATCH_MIN_SHOTS
        if len(matched_shots) >= required:
            if strict_extension:
                reid = _score(best.channels.get("person_reid"))
                appearance = max(
                    _score(best.channels.get("clothing_upper")),
                    _score(best.channels.get("clothing_lower")),
                    _score(best.channels.get("body_hist")),
                )
                if reid < EXTENSION_REID_STRONG or appearance < EXTENSION_APPEARANCE_SUPPORTED:
                    return PairDecision("AMBIGUOUS", best.strength, best.channels, ("dirty-extension-not-strong-enough",))
            return PairDecision("MATCH", best.strength, best.channels, best.reasons)
        if not strict_extension and best.strength >= GALLERY_SINGLE_MATCH_EXCEPTION:
            return PairDecision("MATCH", best.strength, best.channels, best.reasons + ("single-exceptional-gallery-match",))
        return PairDecision("AMBIGUOUS", best.strength, best.channels, ("only-one-gallery-support",))

    if ambiguous:
        best = max(ambiguous, key=lambda decision: decision.strength)
        return PairDecision("AMBIGUOUS", best.strength, best.channels, best.reasons)

    return PairDecision("DIFFERENT", 0.0, {}, ("different-from-gallery",))


def _best_identity_match(
    item: PersonEvidence,
    identities: list[ConfirmedGallery],
    evidence: list[PersonEvidence],
    *,
    strict_extension: bool = False,
) -> tuple[int | None, PairDecision | None, bool]:
    if not identities:
        return None, None, False

    decisions = [
        _gallery_decision(item, identity, evidence, strict_extension=strict_extension)
        for identity in identities
    ]
    matches = [
        (decision.strength, index, decision)
        for index, decision in enumerate(decisions)
        if decision.status == "MATCH"
    ]
    if not matches:
        return None, max(decisions, key=lambda decision: decision.strength), any(
            decision.status == "AMBIGUOUS" for decision in decisions
        )

    matches.sort(reverse=True, key=lambda value: value[0])
    best_strength, best_index, best = matches[0]
    if len(matches) >= 2 and best_strength - matches[1][0] < AMBIGUITY_MARGIN:
        return None, best, True

    # An ambiguous alternative almost as strong as the best match is still unsafe.
    alternatives = [
        decision.strength
        for index, decision in enumerate(decisions)
        if index != best_index and decision.status == "AMBIGUOUS"
    ]
    if alternatives and best_strength - max(alternatives) < AMBIGUITY_MARGIN:
        return None, best, True
    return best_index, best, False


def _seed_group(
    seed_index: int,
    remaining: set[int],
    evidence: list[PersonEvidence],
) -> tuple[set[int], list[float]]:
    seed = evidence[seed_index]
    by_shot: dict[str, tuple[float, int]] = {}
    for index in remaining:
        if index == seed_index:
            continue
        other = evidence[index]
        if other.shot_id == seed.shot_id:
            continue
        decision = compare_person_images(seed, other)
        if decision.status != "MATCH" or decision.hard_conflict:
            continue
        current = by_shot.get(other.shot_id)
        if current is None or decision.strength > current[0]:
            by_shot[other.shot_id] = (decision.strength, index)
    group = {seed_index, *(index for _strength, index in by_shot.values())}
    strengths = [strength for strength, _index in by_shot.values()]
    return group, strengths


def _group_confirmed(indices: set[int], strengths: list[float], evidence: list[PersonEvidence]) -> bool:
    shots = {evidence[index].shot_id for index in indices}
    if len(indices) < CONFIRM_MIN_IMAGES or len(shots) < CONFIRM_MIN_SHOTS:
        return False
    if len(strengths) < CONFIRM_MIN_IMAGES - 1:
        return False
    return median(sorted(strengths, reverse=True)[: min(4, len(strengths))]) >= CONFIRM_MEDIAN_STRENGTH


def _group_is_novel(
    indices: set[int],
    identities: list[ConfirmedGallery],
    evidence: list[PersonEvidence],
) -> bool:
    if not identities:
        return True
    for index in indices:
        item = evidence[index]
        for identity in identities:
            decision = _gallery_decision(item, identity, evidence)
            if decision.status in {"MATCH", "AMBIGUOUS"}:
                return False
    return True


def _absorb_until_stable(
    identities: list[ConfirmedGallery],
    remaining: set[int],
    evidence: list[PersonEvidence],
) -> None:
    changed = True
    while changed and identities:
        changed = False
        for index in sorted(tuple(remaining), key=lambda value: evidence[value].quality, reverse=True):
            identity_index, decision, ambiguous = _best_identity_match(evidence[index], identities, evidence)
            if ambiguous or identity_index is None or decision is None or decision.status != "MATCH":
                continue
            identities[identity_index].evidence_indices.add(index)
            identities[identity_index].strengths.append(decision.strength)
            remaining.remove(index)
            changed = True


def _build_track(source: TrackDraft, observations: list[Observation]) -> TrackDraft:
    value = TrackDraft(
        shot_id=source.shot_id,
        episode_id=source.episode_id,
        episode_order=source.episode_order,
        shot_ordinal=source.shot_ordinal,
        observations=sorted(observations, key=lambda item: item.source_time_us),
    )
    v5._refresh_track(value)
    value.representatives = gallery_v9.select_track_representatives(value)
    return value


def _candidate_gallery(tracks: list[TrackDraft]) -> list[v5.TrackRepresentative]:
    pool = [
        representative
        for track in tracks
        for representative in gallery_v9.select_track_representatives(track)
        if representative.clean
    ]
    pool.sort(key=lambda item: item.quality_score, reverse=True)
    selected: list[v5.TrackRepresentative] = []
    for item in pool:
        if selected and not any(gallery_v9.representatives_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        if len(selected) >= GALLERY_LIMIT:
            break
    return selected


def _refresh_candidate_compatibility(candidate: CandidateDraft) -> None:
    candidate.face_embedding = v5.mean_vector([
        track.face_embedding for track in candidate.tracks if track.face_embedding is not None
    ])
    candidate.reid_embedding = v5.mean_vector([
        track.reid_embedding for track in candidate.tracks if track.reid_embedding is not None
    ])
    candidate.body_hist = v5.mean_vector([
        track.body_hist for track in candidate.tracks if track.body_hist is not None
    ])
    candidate.gallery = _candidate_gallery(candidate.tracks)


def _ephemeral_evidence(track_index: int, observation: Observation) -> PersonEvidence | None:
    bundle = _bundle(observation)
    if bundle is None:
        return None
    return PersonEvidence(
        index=-1,
        track_index=track_index,
        observation=observation,
        bundle=bundle,
        quality=float(getattr(observation, "person_feature_quality", bundle.quality)),
    )


def _assign_all_observations(
    tracks: list[TrackDraft],
    evidence: list[PersonEvidence],
    identities: list[ConfirmedGallery],
) -> tuple[dict[int, dict[int, list[Observation]]], dict[int, list[Observation]]]:
    """Return identity->track->observations plus unresolved observations by track index."""

    assigned_by_object: dict[int, int] = {}
    for identity in identities:
        for evidence_index in identity.evidence_indices:
            assigned_by_object[id(evidence[evidence_index].observation)] = identity.ordinal

    assigned: dict[int, dict[int, list[Observation]]] = {identity.ordinal: {} for identity in identities}
    unresolved: dict[int, list[Observation]] = {}

    for track_index, track in enumerate(tracks):
        for observation in track.observations:
            direct = assigned_by_object.get(id(observation))
            if direct is not None:
                assigned[direct].setdefault(track_index, []).append(observation)
                continue

            item = _ephemeral_evidence(track_index, observation)
            if item is None:
                unresolved.setdefault(track_index, []).append(observation)
                continue
            strict = not _is_clean(observation)
            identity_index, decision, ambiguous = _best_identity_match(
                item,
                identities,
                evidence,
                strict_extension=strict,
            )
            if ambiguous or identity_index is None or decision is None or decision.status != "MATCH":
                unresolved.setdefault(track_index, []).append(observation)
                continue
            ordinal = identities[identity_index].ordinal
            assigned[ordinal].setdefault(track_index, []).append(observation)

    return assigned, unresolved


def _make_candidates(
    tracks: list[TrackDraft],
    evidence: list[PersonEvidence],
    identities: list[ConfirmedGallery],
) -> list[CandidateDraft]:
    assigned, unresolved = _assign_all_observations(tracks, evidence, identities)
    result: list[CandidateDraft] = []

    for identity in identities:
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="RESOLVED")
        candidate.scores = list(identity.strengths)
        for track_index, observations in sorted(assigned.get(identity.ordinal, {}).items()):
            if observations:
                candidate.tracks.append(_build_track(tracks[track_index], observations))
        _refresh_candidate_compatibility(candidate)
        candidate.identity_status = "RESOLVED"  # compatibility refresh must never make face mandatory.
        gallery_members = _gallery_members(identity, evidence)
        candidate.v9_metadata = {  # type: ignore[attr-defined]
            "resolver": "person-gallery-anchor-first-v9c",
            "identity_ordinal": identity.ordinal + 1,
            "seed_instance_id": (
                _instance_id(evidence[identity.seed_index].observation)
                if identity.seed_index is not None else None
            ),
            "confirmed_gallery_images": len(gallery_members),
            "confirmed_gallery_shots": len({item.shot_id for item in gallery_members}),
            "face_images": sum(1 for item in gallery_members if item.bundle.face is not None),
            "policy": (
                "confirm stable Person Gallery -> compare all remaining person images -> "
                "MATCH absorb / AMBIGUOUS unresolved / DIFFERENT may seed next identity"
            ),
            "identity_channels": [
                "person_reid", "clothing_upper", "clothing_lower", "body_hist", "body_structure", "face_optional"
            ],
        }
        result.append(candidate)

    for track_index, observations in sorted(unresolved.items()):
        if not observations:
            continue
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
        candidate.tracks.append(_build_track(tracks[track_index], observations))
        _refresh_candidate_compatibility(candidate)
        candidate.identity_status = "UNRESOLVED"
        candidate.v9_metadata = {  # type: ignore[attr-defined]
            "resolver": "person-gallery-anchor-first-v9c",
            "reason": "not-proven-against-confirmed-person-galleries",
            "policy": "Evidence only; cannot increase Final Character count",
        }
        result.append(candidate)

    result.sort(key=lambda item: (
        0 if item.identity_status == "RESOLVED" else 1,
        min((track.episode_order for track in item.tracks), default=999999),
        min((track.shot_ordinal for track in item.tracks), default=999999),
    ))
    return result


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    ordered_tracks = sorted(
        tracks,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
    evidence = _clean_evidence(ordered_tracks)
    remaining = set(range(len(evidence)))
    identities: list[ConfirmedGallery] = []

    while remaining:
        # Every remaining clean person image must first compare against all confirmed identities.
        _absorb_until_stable(identities, remaining, evidence)
        if not remaining:
            break

        created = False
        for seed_index in sorted(remaining, key=lambda index: evidence[index].quality, reverse=True):
            seed = evidence[seed_index]
            if seed.quality < SEED_MIN_QUALITY:
                continue

            # If the seed is still even ambiguous to an existing gallery, it cannot create A2/B2.
            if identities:
                seed_decisions = [_gallery_decision(seed, identity, evidence) for identity in identities]
                if any(decision.status != "DIFFERENT" for decision in seed_decisions):
                    continue

            group, strengths = _seed_group(seed_index, remaining, evidence)
            if not _group_confirmed(group, strengths, evidence):
                continue
            if not _group_is_novel(group, identities, evidence):
                continue

            identity = ConfirmedGallery(
                ordinal=len(identities),
                evidence_indices=set(group),
                strengths=list(strengths),
                seed_index=seed_index,
            )
            identities.append(identity)
            remaining.difference_update(group)
            created = True
            break

        if not created:
            break

    _absorb_until_stable(identities, remaining, evidence)
    return _make_candidates(ordered_tracks, evidence, identities)
