"""Character V9.1 progressive Person Gallery identity resolver.

V9.1 fixes two remaining single-image assumptions from V9C:
1. a new Character is no longer formed by requiring every supporting Person Image
   to match one seed image directly;
2. after a Character is confirmed, later views are compared against the whole
   multi-view Gallery, not against two fixed-looking representatives.

Formal contracts remain unchanged:
- identity input is isolated Person Instance evidence, never a whole frame;
- Person ReID / clothing / body / optional Face remain separate channels;
- Face is optional supporting evidence, not the identity definition;
- Track count never defines Character count;
- every remaining Person Image compares with confirmed Galleries before a new
  Character can be created;
- partial / occluded / contaminated evidence can extend a confirmed identity only
  under the older strict extension gate and can never seed a Character.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from engine.app import character_identity_v9c as base
from engine.app.character_visual_v5 import CandidateDraft, Observation, TrackDraft
from engine.app.studio_v2 import new_id

PersonEvidence = base.PersonEvidence
PairDecision = base.PairDecision
ConfirmedGallery = base.ConfirmedGallery
compare_person_images = base.compare_person_images

RESOLVER_VERSION = "person-gallery-progressive-v9.1"
CONFIRM_MIN_SHOTS = 3
CONFIRM_MIN_IMAGES = 3
SEED_MIN_QUALITY = base.SEED_MIN_QUALITY
CONFIRM_MEDIAN_STRENGTH = 0.68
GALLERY_LIMIT = base.GALLERY_LIMIT

# Proto-gallery growth is intentionally more tolerant than Final identity creation.
# At least one real MATCH is always required; AMBIGUOUS can only be secondary support.
PROTO_STRONG_SINGLE_MATCH = 0.86
PROTO_MATCH_PLUS_AMBIGUOUS = 0.70

# A proposed new gallery is rejected as a duplicate when an existing gallery has
# strong or repeated positive support. A single ambiguous image cannot veto a
# multi-shot novel gallery anymore.
NOVELTY_STRONG_EXISTING_MATCH = 0.88
NOVELTY_MIN_DIFFERENT_SHOTS = 2


@dataclass(frozen=True)
class ProtoSupport:
    accepted: bool
    strength: float
    match_shots: int
    ambiguous_shots: int
    hard_conflict: bool


def _proto_support(
    item: PersonEvidence,
    group_indices: set[int],
    evidence: list[PersonEvidence],
) -> ProtoSupport:
    """Ask whether one Person Image is supported by an existing set of accepted views."""

    decisions: list[tuple[PersonEvidence, PairDecision]] = []
    for member_index in group_indices:
        member = evidence[member_index]
        if member.shot_id == item.shot_id:
            continue
        decision = compare_person_images(item, member)
        decisions.append((member, decision))

    if not decisions:
        return ProtoSupport(False, 0.0, 0, 0, False)
    if any(decision.hard_conflict for _member, decision in decisions):
        return ProtoSupport(False, 0.0, 0, 0, True)

    match_by_shot: dict[str, float] = {}
    ambiguous_by_shot: dict[str, float] = {}
    for member, decision in decisions:
        if decision.status == "MATCH":
            match_by_shot[member.shot_id] = max(match_by_shot.get(member.shot_id, 0.0), decision.strength)
        elif decision.status == "AMBIGUOUS":
            ambiguous_by_shot[member.shot_id] = max(
                ambiguous_by_shot.get(member.shot_id, 0.0), decision.strength
            )

    if not match_by_shot:
        return ProtoSupport(False, 0.0, 0, len(ambiguous_by_shot), False)

    best_match = max(match_by_shot.values())
    support_values = list(match_by_shot.values()) + list(ambiguous_by_shot.values())
    strength = median(sorted(support_values, reverse=True)[: min(3, len(support_values))])

    if len(match_by_shot) >= 2:
        return ProtoSupport(True, strength, len(match_by_shot), len(ambiguous_by_shot), False)

    if len(ambiguous_by_shot) >= 1 and best_match >= PROTO_MATCH_PLUS_AMBIGUOUS:
        return ProtoSupport(True, strength, 1, len(ambiguous_by_shot), False)

    if best_match >= PROTO_STRONG_SINGLE_MATCH:
        return ProtoSupport(True, best_match, 1, len(ambiguous_by_shot), False)

    return ProtoSupport(False, strength, 1, len(ambiguous_by_shot), False)


def _progressive_gallery_decision(
    item: PersonEvidence,
    identity: ConfirmedGallery,
    evidence: list[PersonEvidence],
) -> PairDecision:
    """Compare one CLEAN Person Image with a confirmed multi-view Person Gallery."""

    strict = base._gallery_decision(item, identity, evidence)
    if strict.status == "MATCH" or strict.hard_conflict:
        return strict

    support = _proto_support(item, identity.evidence_indices, evidence)
    if support.hard_conflict:
        return PairDecision("DIFFERENT", 1.0, strict.channels, ("progressive-gallery-hard-conflict",), True)
    if support.accepted:
        return PairDecision(
            "MATCH",
            support.strength,
            strict.channels,
            (
                "progressive-multiview-gallery-support",
                f"match_shots={support.match_shots}",
                f"ambiguous_shots={support.ambiguous_shots}",
            ),
        )
    return strict


def _best_progressive_identity_match(
    item: PersonEvidence,
    identities: list[ConfirmedGallery],
    evidence: list[PersonEvidence],
) -> tuple[int | None, PairDecision | None, bool]:
    if not identities:
        return None, None, False

    decisions = [_progressive_gallery_decision(item, identity, evidence) for identity in identities]
    matches = [
        (decision.strength, index, decision)
        for index, decision in enumerate(decisions)
        if decision.status == "MATCH"
    ]
    if not matches:
        return None, max(decisions, key=lambda decision: decision.strength), any(
            decision.status == "AMBIGUOUS" for decision in decisions
        )

    matches.sort(reverse=True, key=lambda row: row[0])
    best_strength, best_index, best = matches[0]
    if len(matches) >= 2 and best_strength - matches[1][0] < base.AMBIGUITY_MARGIN:
        return None, best, True

    alternatives = [
        decision.strength
        for index, decision in enumerate(decisions)
        if index != best_index and decision.status == "AMBIGUOUS"
    ]
    if alternatives and best_strength - max(alternatives) < base.AMBIGUITY_MARGIN:
        return None, best, True
    return best_index, best, False


def _absorb_progressively(
    identities: list[ConfirmedGallery],
    remaining: set[int],
    evidence: list[PersonEvidence],
) -> None:
    """Absorb CLEAN evidence through the whole Person Gallery until no assignment changes."""

    changed = True
    while changed and identities:
        changed = False
        for index in sorted(tuple(remaining), key=lambda value: evidence[value].quality, reverse=True):
            identity_index, decision, ambiguous = _best_progressive_identity_match(
                evidence[index], identities, evidence
            )
            if ambiguous or identity_index is None or decision is None or decision.status != "MATCH":
                continue
            identities[identity_index].evidence_indices.add(index)
            identities[identity_index].strengths.append(decision.strength)
            remaining.remove(index)
            changed = True


def _initial_partner(
    seed_index: int,
    remaining: set[int],
    evidence: list[PersonEvidence],
) -> tuple[int | None, float]:
    seed = evidence[seed_index]
    matches: list[tuple[float, float, int]] = []
    for index in remaining:
        if index == seed_index:
            continue
        other = evidence[index]
        if other.shot_id == seed.shot_id:
            continue
        decision = compare_person_images(seed, other)
        if decision.status != "MATCH" or decision.hard_conflict:
            continue
        matches.append((decision.strength, other.quality, index))
    if not matches:
        return None, 0.0
    matches.sort(reverse=True)
    strength, _quality, index = matches[0]
    return index, strength


def _progressive_seed_group(
    seed_index: int,
    remaining: set[int],
    evidence: list[PersonEvidence],
) -> tuple[set[int], list[float]]:
    """Grow a multi-view proto-gallery instead of matching everything to one seed."""

    partner_index, partner_strength = _initial_partner(seed_index, remaining, evidence)
    if partner_index is None:
        return {seed_index}, []

    group = {seed_index, partner_index}
    strengths = [partner_strength]

    while True:
        group_shots = {evidence[member].shot_id for member in group}
        candidates: list[tuple[float, float, int, ProtoSupport]] = []
        for index in remaining - group:
            item = evidence[index]
            if item.shot_id in group_shots:
                continue
            support = _proto_support(item, group, evidence)
            if not support.accepted:
                continue
            candidates.append((support.strength, item.quality, index, support))

        if not candidates:
            break
        candidates.sort(reverse=True, key=lambda row: (row[0], row[1]))
        strength, _quality, index, _support = candidates[0]
        group.add(index)
        strengths.append(strength)

    return group, strengths


def _group_confirmed(
    indices: set[int],
    strengths: list[float],
    evidence: list[PersonEvidence],
) -> bool:
    shots = {evidence[index].shot_id for index in indices}
    if len(indices) < CONFIRM_MIN_IMAGES or len(shots) < CONFIRM_MIN_SHOTS:
        return False
    if len(strengths) < CONFIRM_MIN_IMAGES - 1:
        return False
    top = sorted(strengths, reverse=True)[: min(4, len(strengths))]
    return median(top) >= CONFIRM_MEDIAN_STRENGTH


def _novel_against_identity(
    indices: set[int],
    identity: ConfirmedGallery,
    evidence: list[PersonEvidence],
) -> bool:
    match_shots: dict[str, float] = {}
    ambiguous_shots: set[str] = set()
    different_shots: set[str] = set()

    for index in indices:
        item = evidence[index]
        decision = _progressive_gallery_decision(item, identity, evidence)
        if decision.status == "MATCH":
            match_shots[item.shot_id] = max(match_shots.get(item.shot_id, 0.0), decision.strength)
        elif decision.status == "AMBIGUOUS":
            ambiguous_shots.add(item.shot_id)
        else:
            different_shots.add(item.shot_id)

    # Repeated or exceptionally strong support for A/B means this proposed group is
    # not novel and cannot seed A2/B2.
    if len(match_shots) >= 2:
        return False
    if match_shots and max(match_shots.values()) >= NOVELTY_STRONG_EXISTING_MATCH:
        return False
    if len(match_shots) == 1 and ambiguous_shots:
        return False

    # One ambiguous crop no longer vetoes a whole Character. Require multiple
    # independent shots that are clearly different from the existing gallery.
    return len(different_shots) >= NOVELTY_MIN_DIFFERENT_SHOTS


def _group_is_novel(
    indices: set[int],
    identities: list[ConfirmedGallery],
    evidence: list[PersonEvidence],
) -> bool:
    return all(_novel_against_identity(indices, identity, evidence) for identity in identities)


def _assign_all_observations(
    tracks: list[TrackDraft],
    evidence: list[PersonEvidence],
    identities: list[ConfirmedGallery],
) -> tuple[dict[int, dict[int, list[Observation]]], dict[int, list[Observation]]]:
    """Assign final Track samples; CLEAN uses V9.1 Gallery matching, dirty evidence stays strict."""

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

            item = base._ephemeral_evidence(track_index, observation)
            if item is None:
                unresolved.setdefault(track_index, []).append(observation)
                continue

            if base._is_clean(observation):
                identity_index, decision, ambiguous = _best_progressive_identity_match(item, identities, evidence)
            else:
                identity_index, decision, ambiguous = base._best_identity_match(
                    item,
                    identities,
                    evidence,
                    strict_extension=True,
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
                candidate.tracks.append(base._build_track(tracks[track_index], observations))
        base._refresh_candidate_compatibility(candidate)
        candidate.identity_status = "RESOLVED"
        gallery_members = base._gallery_members(identity, evidence)
        candidate.v9_metadata = {  # type: ignore[attr-defined]
            "resolver": RESOLVER_VERSION,
            "identity_ordinal": identity.ordinal + 1,
            "seed_instance_id": (
                base._instance_id(evidence[identity.seed_index].observation)
                if identity.seed_index is not None else None
            ),
            "confirmed_gallery_images": len(gallery_members),
            "confirmed_gallery_shots": len({item.shot_id for item in gallery_members}),
            "face_images": sum(1 for item in gallery_members if item.bundle.face is not None),
            "gallery_builder": "progressive-proto-gallery",
            "single_seed_identity": False,
            "policy": (
                "seed -> partner -> progressive multi-view gallery; all remaining Person Images compare with "
                "confirmed galleries before a new Character can be created"
            ),
            "novelty_policy": (
                "gallery-level; one ambiguous image cannot veto a clearly novel multi-shot gallery"
            ),
            "identity_channels": [
                "person_reid",
                "clothing_upper",
                "clothing_lower",
                "body_hist",
                "body_structure",
                "face_optional",
            ],
        }
        result.append(candidate)

    for track_index, observations in sorted(unresolved.items()):
        if not observations:
            continue
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
        candidate.tracks.append(base._build_track(tracks[track_index], observations))
        base._refresh_candidate_compatibility(candidate)
        candidate.identity_status = "UNRESOLVED"
        candidate.v9_metadata = {  # type: ignore[attr-defined]
            "resolver": RESOLVER_VERSION,
            "reason": "not-proven-against-confirmed-progressive-person-galleries",
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
    evidence = base._clean_evidence(ordered_tracks)
    remaining = set(range(len(evidence)))
    identities: list[ConfirmedGallery] = []

    while remaining:
        # Core product rule: before creating another Character, every remaining
        # CLEAN Person Image gets a chance to join A/B/C through their whole Gallery.
        _absorb_progressively(identities, remaining, evidence)
        if not remaining:
            break

        created = False
        for seed_index in sorted(remaining, key=lambda index: evidence[index].quality, reverse=True):
            seed = evidence[seed_index]
            if seed.quality < SEED_MIN_QUALITY:
                continue

            # A seed only starts discovery. Build a stable proto-gallery first, then
            # judge novelty against existing Characters at gallery level.
            group, strengths = _progressive_seed_group(seed_index, remaining, evidence)
            if not _group_confirmed(group, strengths, evidence):
                continue
            if identities and not _group_is_novel(group, identities, evidence):
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

    _absorb_progressively(identities, remaining, evidence)
    return _make_candidates(ordered_tracks, evidence, identities)
