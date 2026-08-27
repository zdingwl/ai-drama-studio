"""Character V10 capture-first model classifier.

Pipeline:
1. collect every model-usable Person Instance representative (not CLEAN-only);
2. build identity classes only from reliable whole-person seed evidence;
3. classify remaining front/side/back/occluded/multi-person-frame crops against the
   full identity gallery with Person ReID as the primary model signal;
4. keep clothing/body/optional face as separate supporting evidence;
5. preserve same-sample cannot-link as a hard identity constraint;
6. low-information partial/contaminated images may attach but never seed a Character.

No demographic inference is used for identity classification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

from engine.app import character_gallery_v10 as gallery_v10
from engine.app import character_identity_v9c as v9
from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import observation_policy
from engine.app.character_person_features_v9 import PersonFeatureBundle, feature_channel_scores
from engine.app.studio_v2 import new_id

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft
Observation = v5.Observation
DecisionStatus = Literal["MATCH", "AMBIGUOUS", "DIFFERENT"]

RESOLVER_VERSION = "person-evidence-model-classifier-v10"
CLASSIFIER_MODEL = "YoutuReID person embedding + clothing/body support + optional face"

CONFIRM_MIN_SHOTS = 3
CONFIRM_MIN_IMAGES = 3
GALLERY_LIMIT = 36

REID_STRONG = 0.84
REID_SUPPORTED = 0.74
REID_AMBIGUOUS = 0.60
REID_DIRTY_SINGLE = 0.90
REID_DIRTY_SUPPORTED = 0.79
FACE_CONFLICT = 0.18
FACE_CONFLICT_MIN_SCORE = 0.78
APPEARANCE_SUPPORT = 0.72
AMBIGUITY_MARGIN = 0.055


@dataclass(frozen=True)
class PersonEvidence:
    index: int
    track_index: int
    observation: Observation
    bundle: PersonFeatureBundle
    quality: float
    reliability: float
    seed_eligible: bool

    @property
    def shot_id(self) -> str:
        return str(self.observation.shot_id)


@dataclass(frozen=True)
class ModelDecision:
    status: DecisionStatus
    strength: float
    reid: float | None
    reasons: tuple[str, ...]
    hard_conflict: bool = False


@dataclass
class IdentityClass:
    ordinal: int
    evidence_indices: set[int] = field(default_factory=set)
    seed_index: int | None = None
    support_scores: list[float] = field(default_factory=list)


def _bundle(observation: Observation) -> PersonFeatureBundle | None:
    value = getattr(observation, "person_feature_bundle", None)
    return value if isinstance(value, PersonFeatureBundle) else None


def _cosine(left: Any | None, right: Any | None) -> float | None:
    return v5.cosine(left, right)


def _appearance_support(scores: dict[str, float | None]) -> int:
    return sum(
        1 for name in ("clothing_upper", "clothing_lower", "body_hist", "body_structure")
        if scores.get(name) is not None and float(scores[name]) >= APPEARANCE_SUPPORT
    )


def _face_conflict(left: PersonEvidence, right: PersonEvidence, scores: dict[str, float | None]) -> bool:
    face = scores.get("face")
    return bool(
        left.bundle.face is not None
        and right.bundle.face is not None
        and left.bundle.face_score >= FACE_CONFLICT_MIN_SCORE
        and right.bundle.face_score >= FACE_CONFLICT_MIN_SCORE
        and face is not None
        and float(face) <= FACE_CONFLICT
    )


def compare_person_model(left: PersonEvidence, right: PersonEvidence) -> ModelDecision:
    if v9._cannot_link(left.observation, right.observation):
        return ModelDecision("DIFFERENT", 1.0, None, ("same-sample-cannot-link",), True)

    scores = feature_channel_scores(left.bundle, right.bundle)
    if _face_conflict(left, right, scores):
        return ModelDecision("DIFFERENT", 1.0, scores.get("person_reid"), ("high-quality-face-conflict",), True)

    reid = scores.get("person_reid")
    if reid is None:
        return ModelDecision("AMBIGUOUS", 0.0, None, ("person-reid-missing",))
    reid = float(reid)
    appearance = _appearance_support(scores)

    # Person ReID is the primary model classifier because it is designed for
    # front/side/back person matching.  Other channels support, but do not replace it.
    if reid >= REID_STRONG:
        return ModelDecision("MATCH", reid, reid, ("person-reid-strong",))
    if reid >= REID_SUPPORTED and appearance >= 1:
        return ModelDecision("MATCH", reid, reid, ("person-reid-supported", "appearance-support"))
    if reid >= REID_AMBIGUOUS:
        return ModelDecision("AMBIGUOUS", reid, reid, ("person-reid-ambiguous",))
    return ModelDecision("DIFFERENT", 1.0 - max(0.0, reid), reid, ("person-reid-different",))


def _collect_evidence(tracks: list[TrackDraft]) -> list[PersonEvidence]:
    result: list[PersonEvidence] = []
    for track_index, track in enumerate(tracks):
        representatives = gallery_v10.select_track_representatives(track)
        track.representatives = representatives
        for representative in representatives:
            observation = representative.observation
            policy = observation_policy(observation)
            bundle = _bundle(observation)
            if not policy.evidence_eligible or bundle is None or bundle.person_reid is None:
                continue
            result.append(PersonEvidence(
                index=len(result),
                track_index=track_index,
                observation=observation,
                bundle=bundle,
                quality=float(representative.quality_score),
                reliability=policy.reliability,
                seed_eligible=policy.seed_eligible,
            ))
    return result


def _members(identity: IdentityClass, evidence: list[PersonEvidence]) -> list[PersonEvidence]:
    values = [evidence[index] for index in identity.evidence_indices]
    values.sort(key=lambda item: (item.seed_eligible, item.quality * item.reliability), reverse=True)
    # Avoid one long Shot dominating the class model.
    per_shot: dict[str, int] = {}
    result: list[PersonEvidence] = []
    for item in values:
        if per_shot.get(item.shot_id, 0) >= 2:
            continue
        result.append(item)
        per_shot[item.shot_id] = per_shot.get(item.shot_id, 0) + 1
        if len(result) >= GALLERY_LIMIT:
            break
    return result


def classify_to_identity(item: PersonEvidence, identity: IdentityClass, evidence: list[PersonEvidence]) -> ModelDecision:
    members = _members(identity, evidence)
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
        dirty = not item.seed_eligible
        if dirty:
            if best >= REID_DIRTY_SINGLE or (len(values) >= 2 and median(values[:2]) >= REID_DIRTY_SUPPORTED):
                return ModelDecision("MATCH", best, best, ("reid-model-dirty-view-attach",))
            return ModelDecision("AMBIGUOUS", best, best, ("dirty-view-needs-stronger-model-support",))
        if best >= REID_STRONG or (len(values) >= 2 and median(values[:2]) >= REID_SUPPORTED):
            return ModelDecision("MATCH", best, best, ("reid-model-gallery-match",))
        return ModelDecision("AMBIGUOUS", best, best, ("single-supported-gallery-view",))

    if ambiguous:
        best = max(ambiguous)
        return ModelDecision("AMBIGUOUS", best, best, ("reid-model-gallery-ambiguous",))
    return ModelDecision("DIFFERENT", 0.0, None, ("reid-model-gallery-different",))


def _best_identity(item: PersonEvidence, identities: list[IdentityClass], evidence: list[PersonEvidence]) -> tuple[int | None, ModelDecision | None, bool]:
    if not identities:
        return None, None, False
    decisions = [classify_to_identity(item, identity, evidence) for identity in identities]
    matches = [(decision.strength, index, decision) for index, decision in enumerate(decisions) if decision.status == "MATCH"]
    if not matches:
        ambiguous = any(decision.status == "AMBIGUOUS" for decision in decisions)
        best = max(decisions, key=lambda decision: decision.strength)
        return None, best, ambiguous
    matches.sort(reverse=True, key=lambda row: row[0])
    best_strength, best_index, best = matches[0]
    if len(matches) > 1 and best_strength - matches[1][0] < AMBIGUITY_MARGIN:
        return None, best, True
    alternatives = [
        decision.strength for index, decision in enumerate(decisions)
        if index != best_index and decision.status == "AMBIGUOUS"
    ]
    if alternatives and best_strength - max(alternatives) < AMBIGUITY_MARGIN:
        return None, best, True
    return best_index, best, False


def _grow_seed_group(seed_index: int, available: set[int], evidence: list[PersonEvidence]) -> tuple[set[int], list[float]]:
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
            # The first partner must match the seed directly; later views compare
            # against the entire growing class, so front -> side -> back chains work.
            if len(group) == 1:
                decision = compare_person_model(seed, item)
            else:
                decision = classify_to_identity(item, temp, evidence)
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
    if len(group) < CONFIRM_MIN_IMAGES or len(shots) < CONFIRM_MIN_SHOTS:
        return False
    if len(scores) < CONFIRM_MIN_IMAGES - 1:
        return False
    return median(sorted(scores, reverse=True)[: min(4, len(scores))]) >= REID_SUPPORTED


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
        # One ambiguous view is allowed. A whole proposed class being ambiguous to
        # an existing identity is not enough evidence to create a new Character.
        if len(ambiguous_shots) >= max(2, len(group) - 1):
            return False
    return True


def _absorb(identities: list[IdentityClass], remaining: set[int], evidence: list[PersonEvidence]) -> bool:
    changed = False
    for index in sorted(tuple(remaining), key=lambda value: evidence[value].quality * evidence[value].reliability, reverse=True):
        identity_index, decision, ambiguous = _best_identity(evidence[index], identities, evidence)
        if ambiguous or identity_index is None or decision is None or decision.status != "MATCH":
            continue
        identities[identity_index].evidence_indices.add(index)
        identities[identity_index].support_scores.append(decision.strength)
        remaining.remove(index)
        changed = True
    return changed


def _ephemeral(track_index: int, observation: Observation) -> PersonEvidence | None:
    policy = observation_policy(observation)
    bundle = _bundle(observation)
    if not policy.evidence_eligible or bundle is None or bundle.person_reid is None:
        return None
    return PersonEvidence(
        index=-1,
        track_index=track_index,
        observation=observation,
        bundle=bundle,
        quality=float(getattr(observation, "person_feature_quality", bundle.quality)),
        reliability=policy.reliability,
        seed_eligible=policy.seed_eligible,
    )


def _build_track(source: TrackDraft, observations: list[Observation]) -> TrackDraft:
    value = TrackDraft(
        shot_id=source.shot_id,
        episode_id=source.episode_id,
        episode_order=source.episode_order,
        shot_ordinal=source.shot_ordinal,
        observations=sorted(observations, key=lambda item: item.source_time_us),
    )
    v5._refresh_track(value)
    value.representatives = gallery_v10.select_track_representatives(value)
    return value


def _make_candidates(tracks: list[TrackDraft], evidence: list[PersonEvidence], identities: list[IdentityClass]) -> list[CandidateDraft]:
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
            item = _ephemeral(track_index, observation)
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
                candidate.tracks.append(_build_track(tracks[track_index], observations))
        candidate.face_embedding = v5.mean_vector([track.face_embedding for track in candidate.tracks if track.face_embedding is not None])
        candidate.reid_embedding = v5.mean_vector([track.reid_embedding for track in candidate.tracks if track.reid_embedding is not None])
        candidate.body_hist = v5.mean_vector([track.body_hist for track in candidate.tracks if track.body_hist is not None])
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
            "instance_classes": sorted({str(getattr(rep.observation, "instance_class", "UNKNOWN")) for rep in candidate.gallery}),
            "policy": "capture usable Person Instances first -> model classify to identity -> persist multi-view person gallery",
            "face_required": False,
        }
        result.append(candidate)

    for track_index, observations in sorted(unresolved.items()):
        if not observations:
            continue
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
        candidate.tracks.append(_build_track(tracks[track_index], observations))
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
    evidence = _collect_evidence(ordered_tracks)
    remaining = set(range(len(evidence)))
    identities: list[IdentityClass] = []

    while remaining:
        while _absorb(identities, remaining, evidence):
            pass
        seed_pool = {index for index in remaining if evidence[index].seed_eligible}
        if not seed_pool:
            break

        created = False
        for seed_index in sorted(seed_pool, key=lambda index: evidence[index].quality * evidence[index].reliability, reverse=True):
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
