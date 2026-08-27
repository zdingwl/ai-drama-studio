"""Character V10.1 identity classifier.

V10.1 keeps V10 capture-first semantics, but removes the incorrect assumption that
image-condition labels decide whether a real person may ever become an identity.
Strong CONTAMINATED / substantial PARTIAL person crops may propose an identity only
when they form a stable cross-shot Person-ReID class. Tiny/weak partials remain
attach-only. Same-sample cannot-link stays a hard negative constraint.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from engine.app import character_gallery_v10 as gallery_v10
from engine.app import character_identity_v10 as base
from engine.app import character_identity_v9c as v9
from engine.app import character_visual_v5 as v5
from engine.app.character_person_features_v9 import feature_channel_scores
from engine.app.studio_v2 import new_id

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft
Observation = v5.Observation
PersonEvidence = base.PersonEvidence
ModelDecision = base.ModelDecision
IdentityClass = base.IdentityClass

RESOLVER_VERSION = "person-evidence-model-classifier-v10.1"
CLASSIFIER_MODEL = base.CLASSIFIER_MODEL

RISKY_CLASSES = {"CONTAMINATED", "PARTIAL"}
RISKY_DIRECT_STRONG = 0.88
RISKY_SUPPORTED = 0.80
RISKY_AMBIGUOUS = 0.62
RISKY_APPEARANCE_CHANNELS = 2
RISKY_GROUP_CONFIRM = 0.84


def _instance_class(item: PersonEvidence) -> str:
    return str(getattr(item.observation, "instance_class", "UNKNOWN") or "UNKNOWN").upper()


def _risky(item: PersonEvidence) -> bool:
    return _instance_class(item) in RISKY_CLASSES


def compare_person_model(left: PersonEvidence, right: PersonEvidence) -> ModelDecision:
    if v9._cannot_link(left.observation, right.observation):
        return ModelDecision("DIFFERENT", 1.0, None, ("same-sample-cannot-link",), True)

    scores = feature_channel_scores(left.bundle, right.bundle)
    if base._face_conflict(left, right, scores):
        return ModelDecision(
            "DIFFERENT",
            1.0,
            scores.get("person_reid"),
            ("high-quality-face-conflict",),
            True,
        )

    if not (_risky(left) or _risky(right)):
        return base.compare_person_model(left, right)

    reid = scores.get("person_reid")
    if reid is None:
        return ModelDecision("AMBIGUOUS", 0.0, None, ("person-reid-missing",))
    reid = float(reid)
    appearance = base._appearance_support(scores)

    # Risky image conditions are allowed to participate, but a single noisy crop
    # must not be enough to create/attach a person identity.
    if reid >= RISKY_DIRECT_STRONG:
        return ModelDecision("MATCH", reid, reid, ("risky-person-reid-strong",))
    if reid >= RISKY_SUPPORTED and appearance >= RISKY_APPEARANCE_CHANNELS:
        return ModelDecision(
            "MATCH",
            reid,
            reid,
            ("risky-person-reid-supported", "multi-channel-appearance-support"),
        )
    if reid >= RISKY_AMBIGUOUS:
        return ModelDecision("AMBIGUOUS", reid, reid, ("risky-person-reid-ambiguous",))
    return ModelDecision("DIFFERENT", 1.0 - max(0.0, reid), reid, ("risky-person-reid-different",))


def classify_to_identity(
    item: PersonEvidence,
    identity: IdentityClass,
    evidence: list[PersonEvidence],
) -> ModelDecision:
    members = base._members(identity, evidence)
    decisions = [(member, compare_person_model(item, member)) for member in members if member.index != item.index]
    if not decisions:
        return ModelDecision("DIFFERENT", 0.0, None, ("empty-identity-gallery",))

    hard = [decision for _member, decision in decisions if decision.hard_conflict]
    if hard:
        return hard[0]

    by_shot: dict[str, float] = {}
    ambiguous: list[float] = []
    for member, decision in decisions:
        if decision.status == "MATCH" and decision.reid is not None:
            by_shot[member.shot_id] = max(by_shot.get(member.shot_id, -1.0), float(decision.reid))
        elif decision.status == "AMBIGUOUS" and decision.reid is not None:
            ambiguous.append(float(decision.reid))

    if by_shot:
        values = sorted(by_shot.values(), reverse=True)
        best = values[0]
        if _risky(item):
            if best >= base.REID_DIRTY_SINGLE or (
                len(values) >= 2 and median(values[:2]) >= base.REID_DIRTY_SUPPORTED
            ):
                return ModelDecision("MATCH", best, best, ("risky-view-gallery-attach",))
            return ModelDecision("AMBIGUOUS", best, best, ("risky-view-needs-stronger-gallery-support",))
        if best >= base.REID_STRONG or (
            len(values) >= 2 and median(values[:2]) >= base.REID_SUPPORTED
        ):
            return ModelDecision("MATCH", best, best, ("reid-model-gallery-match",))
        return ModelDecision("AMBIGUOUS", best, best, ("single-supported-gallery-view",))

    if ambiguous:
        best = max(ambiguous)
        return ModelDecision("AMBIGUOUS", best, best, ("reid-model-gallery-ambiguous",))
    return ModelDecision("DIFFERENT", 0.0, None, ("reid-model-gallery-different",))


def _best_identity(
    item: PersonEvidence,
    identities: list[IdentityClass],
    evidence: list[PersonEvidence],
) -> tuple[int | None, ModelDecision | None, bool]:
    if not identities:
        return None, None, False
    decisions = [classify_to_identity(item, identity, evidence) for identity in identities]
    matches = [
        (decision.strength, index, decision)
        for index, decision in enumerate(decisions)
        if decision.status == "MATCH"
    ]
    if not matches:
        ambiguous = any(decision.status == "AMBIGUOUS" for decision in decisions)
        best = max(decisions, key=lambda decision: decision.strength)
        return None, best, ambiguous
    matches.sort(reverse=True, key=lambda row: row[0])
    best_strength, best_index, best = matches[0]
    if len(matches) > 1 and best_strength - matches[1][0] < base.AMBIGUITY_MARGIN:
        return None, best, True
    alternatives = [
        decision.strength
        for index, decision in enumerate(decisions)
        if index != best_index and decision.status == "AMBIGUOUS"
    ]
    if alternatives and best_strength - max(alternatives) < base.AMBIGUITY_MARGIN:
        return None, best, True
    return best_index, best, False


def _grow_seed_group(
    seed_index: int,
    available: set[int],
    evidence: list[PersonEvidence],
) -> tuple[set[int], list[float]]:
    seed = evidence[seed_index]
    group = {seed_index}
    scores: list[float] = []

    while True:
        candidates: list[tuple[float, float, int]] = []
        temp = IdentityClass(ordinal=-1, evidence_indices=set(group), seed_index=seed_index)
        current_shots = {evidence[index].shot_id for index in group}
        for index in available - group:
            item = evidence[index]
            if not item.seed_eligible or item.shot_id in current_shots:
                continue
            decision = (
                compare_person_model(seed, item)
                if len(group) == 1
                else classify_to_identity(item, temp, evidence)
            )
            if decision.status != "MATCH" or decision.hard_conflict:
                continue
            candidates.append((decision.strength, item.quality * item.reliability, index))
        if not candidates:
            break
        candidates.sort(reverse=True)
        strength, _quality, index = candidates[0]
        group.add(index)
        scores.append(strength)

    return group, scores


def _group_confirmed(group: set[int], scores: list[float], evidence: list[PersonEvidence]) -> bool:
    shots = {evidence[index].shot_id for index in group}
    if len(group) < base.CONFIRM_MIN_IMAGES or len(shots) < base.CONFIRM_MIN_SHOTS:
        return False
    if len(scores) < base.CONFIRM_MIN_IMAGES - 1:
        return False
    threshold = RISKY_GROUP_CONFIRM if any(_risky(evidence[index]) for index in group) else base.REID_SUPPORTED
    return median(sorted(scores, reverse=True)[: min(4, len(scores))]) >= threshold


def _group_novel(group: set[int], identities: list[IdentityClass], evidence: list[PersonEvidence]) -> bool:
    if not identities:
        return True
    for identity in identities:
        matched_shots: set[str] = set()
        ambiguous_shots: set[str] = set()
        different_shots: set[str] = set()
        for index in group:
            item = evidence[index]
            decision = classify_to_identity(item, identity, evidence)
            if decision.status == "MATCH":
                matched_shots.add(item.shot_id)
            elif decision.status == "AMBIGUOUS":
                ambiguous_shots.add(item.shot_id)
            else:
                different_shots.add(item.shot_id)
        if len(matched_shots) >= 2:
            return False
        if len(different_shots) < 2:
            return False
        if len(ambiguous_shots) >= max(2, len(group) - 1):
            return False
    return True


def _absorb(identities: list[IdentityClass], remaining: set[int], evidence: list[PersonEvidence]) -> bool:
    changed = False
    for index in sorted(
        tuple(remaining),
        key=lambda value: evidence[value].quality * evidence[value].reliability,
        reverse=True,
    ):
        identity_index, decision, ambiguous = _best_identity(evidence[index], identities, evidence)
        if ambiguous or identity_index is None or decision is None or decision.status != "MATCH":
            continue
        identities[identity_index].evidence_indices.add(index)
        identities[identity_index].support_scores.append(decision.strength)
        remaining.remove(index)
        changed = True
    return changed


def _make_candidates(
    tracks: list[TrackDraft],
    evidence: list[PersonEvidence],
    identities: list[IdentityClass],
) -> list[CandidateDraft]:
    direct: dict[int, int] = {}
    for identity in identities:
        for index in identity.evidence_indices:
            direct[id(evidence[index].observation)] = identity.ordinal

    assigned: dict[int, dict[int, list[Observation]]] = {identity.ordinal: {} for identity in identities}
    unresolved: dict[int, list[Observation]] = {}

    for track_index, track in enumerate(tracks):
        for observation in track.observations:
            ordinal = direct.get(id(observation))
            if ordinal is not None:
                assigned[ordinal].setdefault(track_index, []).append(observation)
                continue
            item = base._ephemeral(track_index, observation)
            if item is None:
                unresolved.setdefault(track_index, []).append(observation)
                continue
            identity_index, decision, ambiguous = _best_identity(item, identities, evidence)
            if ambiguous or identity_index is None or decision is None or decision.status != "MATCH":
                unresolved.setdefault(track_index, []).append(observation)
                continue
            ordinal = identities[identity_index].ordinal
            assigned[ordinal].setdefault(track_index, []).append(observation)

    result: list[CandidateDraft] = []
    for identity in identities:
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="RESOLVED")
        candidate.scores = list(identity.support_scores)
        for track_index, observations in sorted(assigned.get(identity.ordinal, {}).items()):
            if observations:
                candidate.tracks.append(base._build_track(tracks[track_index], observations))
        candidate.face_embedding = v5.mean_vector([
            track.face_embedding for track in candidate.tracks if track.face_embedding is not None
        ])
        candidate.reid_embedding = v5.mean_vector([
            track.reid_embedding for track in candidate.tracks if track.reid_embedding is not None
        ])
        candidate.body_hist = v5.mean_vector([
            track.body_hist for track in candidate.tracks if track.body_hist is not None
        ])
        candidate.gallery = gallery_v10.select_candidate_gallery(candidate.tracks)
        candidate.identity_status = "RESOLVED"
        seed_members = [evidence[index] for index in identity.evidence_indices]
        candidate.v10_metadata = {  # type: ignore[attr-defined]
            "resolver": RESOLVER_VERSION,
            "classifier_model": CLASSIFIER_MODEL,
            "identity_ordinal": identity.ordinal + 1,
            "captured_classified_images": len(candidate.gallery),
            "confirmed_gallery_images": len(seed_members),
            "confirmed_gallery_shots": len({item.shot_id for item in seed_members}),
            "classified_shots": len({track.shot_id for track in candidate.tracks}),
            "instance_classes": sorted({
                str(getattr(rep.observation, "instance_class", "UNKNOWN"))
                for rep in candidate.gallery
            }),
            "seed_instance_classes": sorted({_instance_class(item) for item in seed_members}),
            "risky_seed_confirmation": any(_risky(item) for item in seed_members),
            "policy": (
                "capture usable Person Instances first -> model classify to identity; "
                "strong contaminated/substantial partial views require stricter cross-shot confirmation"
            ),
            "face_required": False,
        }
        result.append(candidate)

    for track_index, observations in sorted(unresolved.items()):
        if not observations:
            continue
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
        candidate.tracks.append(base._build_track(tracks[track_index], observations))
        candidate.gallery = gallery_v10.select_candidate_gallery(candidate.tracks)
        candidate.identity_status = "UNRESOLVED"
        candidate.v10_metadata = {  # type: ignore[attr-defined]
            "resolver": RESOLVER_VERSION,
            "reason": "person model classification not confident enough",
            "policy": "Evidence retained; does not increase Final Character count",
        }
        result.append(candidate)

    result.sort(key=lambda item: (
        0 if item.identity_status == "RESOLVED" else 1,
        min((track.episode_order for track in item.tracks), default=999999),
        min((track.shot_ordinal for track in item.tracks), default=999999),
    ))
    return result


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    ordered_tracks = sorted(tracks, key=lambda item: (
        item.episode_order,
        item.shot_ordinal,
        item.start_us if item.start_us is not None else -1,
    ))
    evidence = base._collect_evidence(ordered_tracks)
    remaining = set(range(len(evidence)))
    identities: list[IdentityClass] = []

    while remaining:
        while _absorb(identities, remaining, evidence):
            pass
        seed_pool = {index for index in remaining if evidence[index].seed_eligible}
        if not seed_pool:
            break

        created = False
        for seed_index in sorted(
            seed_pool,
            key=lambda index: evidence[index].quality * evidence[index].reliability,
            reverse=True,
        ):
            group, scores = _grow_seed_group(seed_index, seed_pool, evidence)
            if not _group_confirmed(group, scores, evidence):
                continue
            if not _group_novel(group, identities, evidence):
                continue
            identity = IdentityClass(
                ordinal=len(identities),
                evidence_indices=set(group),
                seed_index=seed_index,
                support_scores=list(scores),
            )
            identities.append(identity)
            remaining.difference_update(group)
            created = True
            break
        if not created:
            break

    while _absorb(identities, remaining, evidence):
        pass
    return _make_candidates(ordered_tracks, evidence, identities)


__all__ = [
    "RESOLVER_VERSION",
    "CLASSIFIER_MODEL",
    "PersonEvidence",
    "ModelDecision",
    "IdentityClass",
    "compare_person_model",
    "classify_to_identity",
    "resolve_global_identities",
]
