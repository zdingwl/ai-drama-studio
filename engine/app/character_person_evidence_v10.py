"""Character V10 Person Evidence policy.

V10 follows capture-first, classify-second:
- every detector-backed Person Instance is preserved as person evidence when it has
  enough visible body information for model comparison;
- CLEAN is not a prerequisite for evidence storage or identity classification;
- seed eligibility is a separate, stricter property used only when creating a new
  identity class;
- side/back views and people split from a multi-person frame are first-class evidence;
- partial/occluded/contaminated views may attach to an existing identity with stronger
  model support, but low-information fragments do not create a new Character.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CLASS_RELIABILITY = {
    "CLEAN": 1.00,
    "OCCLUDED": 0.82,
    "CONTAMINATED": 0.62,
    "PARTIAL": 0.50,
}

MIN_EVIDENCE_QUALITY = 0.28
MIN_SEED_QUALITY = 0.58
MIN_PARTIAL_AREA_RATIO = 0.012
MIN_OTHER_AREA_RATIO = 0.008


@dataclass(frozen=True)
class PersonEvidencePolicy:
    evidence_eligible: bool
    seed_eligible: bool
    reliability: float
    reason: str


def observation_policy(observation: Any) -> PersonEvidencePolicy:
    instance_class = str(getattr(observation, "instance_class", "UNKNOWN") or "UNKNOWN")
    reliability = float(CLASS_RELIABILITY.get(instance_class, 0.40))
    quality = float(getattr(observation, "person_feature_quality", 0.0) or 0.0)
    frame_area = max(1, int(getattr(observation, "frame_width", 1)) * int(getattr(observation, "frame_height", 1)))
    bbox = tuple(int(value) for value in getattr(observation, "person_bbox", getattr(observation, "bbox", (0, 0, 0, 0))))
    area_ratio = max(0, bbox[2]) * max(0, bbox[3]) / float(frame_area)
    source = str(getattr(observation, "detection_source", "") or "").lower()
    bundle = getattr(observation, "person_feature_bundle", None)
    reid = getattr(bundle, "person_reid", None) if bundle is not None else None

    # Face fallback is useful auxiliary evidence, but it is not a detector-backed
    # person image and therefore cannot represent a side/back/full-body identity.
    if "face-fallback" in source:
        return PersonEvidencePolicy(False, False, 0.0, "synthetic face fallback is not a person-image instance")
    if bundle is None or reid is None:
        return PersonEvidencePolicy(False, False, reliability, "person model feature is missing")

    min_area = MIN_PARTIAL_AREA_RATIO if instance_class == "PARTIAL" else MIN_OTHER_AREA_RATIO
    if area_ratio < min_area:
        return PersonEvidencePolicy(False, False, reliability, "visible person area is too small")
    if quality < MIN_EVIDENCE_QUALITY:
        return PersonEvidencePolicy(False, False, reliability, "person-image quality is too low")

    evidence_eligible = True
    # A new identity may be seeded from isolated or moderately occluded whole-person
    # views.  Contaminated/partial images are still saved and classified, but they
    # cannot independently create a new Character.
    seed_eligible = bool(
        instance_class in {"CLEAN", "OCCLUDED"}
        and quality >= MIN_SEED_QUALITY
    )
    reason = "capture-first person evidence"
    if not seed_eligible:
        reason += "; classify/attach only"
    return PersonEvidencePolicy(evidence_eligible, seed_eligible, reliability, reason)


def attach_v10_policy(observation: Any) -> Any:
    policy = observation_policy(observation)
    observation.person_evidence_eligible = policy.evidence_eligible
    observation.person_seed_eligible = policy.seed_eligible
    observation.person_evidence_reliability = policy.reliability
    observation.person_evidence_reason = policy.reason
    return observation
