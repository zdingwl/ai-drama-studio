"""Character V9.1 progressive Person Gallery identity resolver.

Why V9.1 exists:
V9C still formed a new identity by requiring every supporting Person Image to match
one seed image directly.  That is too close to single-image identity matching: the
same person may move from frontal -> profile -> looking down and no single image is
a good visual anchor for every view.

V9.1 keeps the V9 contracts but changes gallery formation:
- a high-quality seed only starts a proto-gallery;
- the seed must first find one strong cross-shot partner;
- the proto-gallery then grows progressively from multiple already accepted views;
- one image being AMBIGUOUS to an existing Character does not veto an otherwise
  clearly novel multi-shot gallery; novelty is judged from the gallery as a whole;
- strong/multi-shot matches to an existing gallery still block A -> A2 duplication;
- partial / occluded / contaminated evidence can never seed a Character.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from engine.app import character_identity_v9c as base
from engine.app.character_visual_v5 import CandidateDraft, TrackDraft

PersonEvidence = base.PersonEvidence
PairDecision = base.PairDecision
ConfirmedGallery = base.ConfirmedGallery
compare_person_images = base.compare_person_images

RESOLVER_VERSION = "person-gallery-progressive-v9.1"
CONFIRM_MIN_SHOTS = 3
CONFIRM_MIN_IMAGES = 3
SEED_MIN_QUALITY = base.SEED_MIN_QUALITY
CONFIRM_MEDIAN_STRENGTH = 0.68

# Proto-gallery growth is intentionally more tolerant than Final gallery identity.
# At least one real MATCH is always required; AMBIGUOUS can only be secondary support.
PROTO_STRONG_SINGLE_MATCH = 0.86
PROTO_MATCH_PLUS_AMBIGUOUS = 0.70

# A proposed new gallery is rejected as a duplicate when an existing gallery has
# strong or repeated positive support.  A single ambiguous image cannot veto a
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

    # Mature proto-gallery evidence: match two independent accepted views.
    if len(match_by_shot) >= 2:
        return ProtoSupport(True, strength, len(match_by_shot), len(ambiguous_by_shot), False)

    # One strong match plus another independent ambiguous view is enough to extend
    # the proto-gallery.  The group still needs >=3 independent Shots to confirm.
    if len(ambiguous_by_shot) >= 1 and best_match >= PROTO_MATCH_PLUS_AMBIGUOUS:
        return ProtoSupport(True, strength, 1, len(ambiguous_by_shot), False)

    # A very strong cross-shot Person Image match may add one new viewpoint.  This
    # is useful for frontal -> profile -> looking-down chains where adjacent views
    # match strongly but the endpoints do not.
    if best_match >= PROTO_STRONG_SINGLE_MATCH:
        return ProtoSupport(True, best_match, 1, len(ambiguous_by_shot), False)

    return ProtoSupport(False, strength, 1, len(ambiguous_by_shot), False)


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
        candidates: list[tuple[float, float, int, ProtoSupport]] = []
        for index in remaining - group:
            item = evidence[index]
            # During confirmation one representative per Shot is enough.  Other
            # same-Shot images can be absorbed after the Character is confirmed.
            if item.shot_id in {evidence[member].shot_id for member in group}:
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
    hard_different_shots: set[str] = set()

    for index in indices:
        item = evidence[index]
        decision = base._gallery_decision(item, identity, evidence)
        if decision.status == "MATCH":
            match_shots[item.shot_id] = max(match_shots.get(item.shot_id, 0.0), decision.strength)
        elif decision.status == "AMBIGUOUS":
            ambiguous_shots.add(item.shot_id)
        else:
            different_shots.add(item.shot_id)
            if decision.hard_conflict:
                hard_different_shots.add(item.shot_id)

    # Repeated evidence that the proposed group is already A/B means it cannot seed A2/B2.
    if len(match_shots) >= 2:
        return False
    if match_shots and max(match_shots.values()) >= NOVELTY_STRONG_EXISTING_MATCH:
        return False
    if len(match_shots) == 1 and ambiguous_shots:
        return False

    # One ambiguous crop no longer vetoes a whole new Character.  Require multiple
    # independent shots that are clearly different from this existing gallery.
    if len(different_shots) >= NOVELTY_MIN_DIFFERENT_SHOTS:
        return True

    # A same-sample / high-quality-face hard conflict is strong negative identity
    # evidence, but still require another independent non-match shot before creating
    # a new automatic Character.
    if hard_different_shots and len(different_shots | hard_different_shots) >= 2:
        return True

    return False


def _group_is_novel(
    indices: set[int],
    identities: list[ConfirmedGallery],
    evidence: list[PersonEvidence],
) -> bool:
    return all(_novel_against_identity(indices, identity, evidence) for identity in identities)


def _decorate_candidates(candidates: list[CandidateDraft]) -> list[CandidateDraft]:
    for candidate in candidates:
        metadata = dict(getattr(candidate, "v9_metadata", {}) or {})
        metadata["resolver"] = RESOLVER_VERSION
        metadata["gallery_builder"] = "progressive-proto-gallery"
        metadata["single_seed_identity"] = False
        metadata["novelty_policy"] = "gallery-level; one ambiguous image cannot veto a clearly novel multi-shot gallery"
        candidate.v9_metadata = metadata  # type: ignore[attr-defined]
    return candidates


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
        # First obey the user's core rule: every remaining image compares with all
        # already confirmed Person Galleries before a new Character is considered.
        base._absorb_until_stable(identities, remaining, evidence)
        if not remaining:
            break

        created = False
        for seed_index in sorted(remaining, key=lambda index: evidence[index].quality, reverse=True):
            seed = evidence[seed_index]
            if seed.quality < SEED_MIN_QUALITY:
                continue

            # Do NOT let one seed image decide novelty. Build a stable Person Gallery
            # first; then judge that gallery against A/B/C as a whole.
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

    base._absorb_until_stable(identities, remaining, evidence)
    return _decorate_candidates(base._make_candidates(ordered_tracks, evidence, identities))
