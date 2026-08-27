"""Character V10 classified Person Gallery.

A V10 gallery is not a pre-identity CLEAN filter.  It is the collection of useful
Person Instance views already classified to one identity.  Front/side/back views and
people split from multi-person frames may all be persisted.  Instance class and
reliability stay explicit so low-quality/overlapped evidence never becomes invisible.
"""
from __future__ import annotations

import json
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import observation_policy
from engine.app.character_person_features_v9 import FEATURE_VERSION, feature_channel_scores, feature_dimensions
from engine.app.studio_v2 import workspace_root

Observation = v5.Observation
TrackDraft = v5.TrackDraft
TrackRepresentative = v5.TrackRepresentative
CandidateDraft = v5.CandidateDraft

GALLERY_LIMIT = 36
SAME_SHOT_MIN_TIME_GAP_US = 500_000
DIVERSITY_THRESHOLDS = {
    "person_reid": 0.975,
    "clothing_upper": 0.95,
    "clothing_lower": 0.95,
    "body_hist": 0.96,
    "body_structure": 0.94,
    "face": 0.965,
}


def _evidence_eligible(observation: Observation) -> bool:
    explicit = getattr(observation, "person_evidence_eligible", None)
    if explicit is not None:
        return bool(explicit)
    return observation_policy(observation).evidence_eligible


def _reliability(observation: Observation) -> float:
    explicit = getattr(observation, "person_evidence_reliability", None)
    if explicit is not None:
        return max(0.0, min(1.0, float(explicit)))
    return observation_policy(observation).reliability


def _quality(observation: Observation) -> float:
    raw = getattr(observation, "person_feature_quality", None)
    if raw is None:
        raw = v5._representative_quality(observation)
    # Reliability affects ranking, not whether a valid back/side view is saved.
    return max(0.0, min(1.0, float(raw))) * (0.72 + 0.28 * _reliability(observation))


def representatives_diverse(left: TrackRepresentative, right: TrackRepresentative) -> bool:
    a = left.observation
    b = right.observation
    if a.shot_id != b.shot_id:
        return True
    if str(getattr(a, "instance_class", "")) != str(getattr(b, "instance_class", "")):
        return True
    left_bundle = getattr(a, "person_feature_bundle", None)
    right_bundle = getattr(b, "person_feature_bundle", None)
    if left_bundle is not None and right_bundle is not None:
        scores = feature_channel_scores(left_bundle, right_bundle)
        for channel, threshold in DIVERSITY_THRESHOLDS.items():
            score = scores.get(channel)
            if score is not None and float(score) < threshold:
                return True
    return abs(int(a.source_time_us) - int(b.source_time_us)) >= SAME_SHOT_MIN_TIME_GAP_US


def select_track_representatives(track: TrackDraft) -> list[TrackRepresentative]:
    """Select useful model-classified views; CLEAN is not required."""

    scored = [
        TrackRepresentative(
            observation=item,
            quality_score=_quality(item),
            # Historical field name. In V10 it means usable person evidence, not CLEAN.
            clean=_evidence_eligible(item),
        )
        for item in track.observations
        if isinstance(item, Observation) and _evidence_eligible(item)
    ]
    scored.sort(
        key=lambda item: (
            1 if bool(getattr(item.observation, "person_seed_eligible", False)) else 0,
            item.quality_score,
        ),
        reverse=True,
    )
    selected: list[TrackRepresentative] = []
    for item in scored:
        if selected and not any(representatives_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        if len(selected) >= v5.TRACK_GALLERY_LIMIT:
            break
    return selected


def select_candidate_gallery(tracks: list[TrackDraft], *, limit: int = GALLERY_LIMIT) -> list[TrackRepresentative]:
    pool = [representative for track in tracks for representative in select_track_representatives(track)]
    pool.sort(
        key=lambda item: (
            1 if bool(getattr(item.observation, "person_seed_eligible", False)) else 0,
            item.quality_score,
        ),
        reverse=True,
    )
    selected: list[TrackRepresentative] = []
    per_shot: dict[str, int] = {}
    for item in pool:
        shot_id = str(item.observation.shot_id)
        if per_shot.get(shot_id, 0) >= 3:
            continue
        if selected and not any(representatives_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        per_shot[shot_id] = per_shot.get(shot_id, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def _crop_observation(observation: Observation):
    frame = v5._read_frame(observation.reference_path, observation.local_time_us)
    if frame is None:
        return None, None
    height, width = frame.shape[:2]
    box = tuple(int(value) for value in getattr(observation, "person_crop_bbox", observation.bbox))
    x, y, w, h = box
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    right = max(x + 1, min(width, x + max(1, w)))
    bottom = max(y + 1, min(height, y + max(1, h)))
    crop = frame[y:bottom, x:right]
    if crop.size == 0:
        return None, None
    return crop, (x, y, right - x, bottom - y)


def _save_feature_sidecar(root: Any, index: int, observation: Observation) -> tuple[str | None, dict[str, int]]:
    bundle = getattr(observation, "person_feature_bundle", None)
    if bundle is None:
        return None, {}
    import numpy as np

    arrays = {
        name: getattr(bundle, name)
        for name in ("person_reid", "clothing_upper", "clothing_lower", "body_hist", "body_structure", "face")
        if getattr(bundle, name) is not None
    }
    if not arrays:
        return None, {}
    path = root / f"features_{index:03d}.npz"
    np.savez_compressed(str(path), **{name: np.asarray(value, dtype=np.float32) for name, value in arrays.items()})
    return str(path), feature_dimensions(bundle)


def save_candidate_gallery(run_id: str, candidate: CandidateDraft, ordinal: int) -> list[str]:
    """Persist classified multi-view Person crops and per-image model features."""

    import cv2

    root = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}"
    root.mkdir(parents=True, exist_ok=True)
    gallery = list(getattr(candidate, "gallery", []) or []) or select_candidate_gallery(candidate.tracks)
    saved: list[str] = []
    manifest_images: list[dict[str, object]] = []
    for index, representative in enumerate(gallery, start=1):
        observation = representative.observation
        if not _evidence_eligible(observation):
            continue
        crop, crop_bbox = _crop_observation(observation)
        if crop is None or crop_bbox is None:
            continue
        path = root / f"gallery_{index:03d}.jpg"
        if not cv2.imwrite(str(path), crop):
            continue
        saved.append(str(path))
        feature_path, dimensions = _save_feature_sidecar(root, index, observation)
        bundle = getattr(observation, "person_feature_bundle", None)
        policy = observation_policy(observation)
        manifest_images.append({
            "path": str(path),
            "feature_path": feature_path,
            "feature_version": getattr(bundle, "feature_version", FEATURE_VERSION) if bundle is not None else FEATURE_VERSION,
            "feature_channels": list(getattr(bundle, "available_channels", ()) or ()),
            "feature_dimensions": dimensions,
            "shot_id": observation.shot_id,
            "source_time_us": int(observation.source_time_us),
            "instance_id": getattr(observation, "instance_id", None),
            "person_bbox": list(getattr(observation, "person_bbox", observation.bbox)),
            "crop_bbox": list(crop_bbox),
            "quality": round(float(representative.quality_score), 6),
            "instance_class": str(getattr(observation, "instance_class", "UNKNOWN")),
            "evidence_eligible": policy.evidence_eligible,
            "seed_eligible": policy.seed_eligible,
            "reliability": round(policy.reliability, 6),
            "face_visible": bool(observation.face_visible),
            "face_score": round(float(getattr(observation, "face_score", 0.0)), 6),
            "source": "classified-person-instance-crop",
        })

    (root / "gallery.json").write_text(json.dumps({
        "candidate_id": candidate.id,
        "identity_status": candidate.identity_status,
        "feature_version": FEATURE_VERSION,
        "policy": "V10 capture all usable Person Instances -> model classify -> persist multi-view classified gallery",
        "image_count": len(manifest_images),
        "images": manifest_images,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    paths = save_candidate_gallery(run_id, candidate, ordinal)
    return paths[0] if paths else None
