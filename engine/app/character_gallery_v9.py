"""Character V9 Phase A/B gallery safety and feature persistence.

Phase A: only CLEAN Person Instance crops can enter a formal person gallery.
Phase B: every saved gallery image keeps its multi-channel person features in a
compressed sidecar so identity logic can compare ReID/clothing/body/face channels
separately without recomputing from a whole frame.
"""
from __future__ import annotations

import json

from engine.app import character_visual_v5 as v5
from engine.app.character_person_features_v9 import (
    FEATURE_VERSION,
    feature_channel_scores,
    feature_dimensions,
)
from engine.app.character_person_instance_v9 import classify_person_instance, gallery_crop_is_valid
from engine.app.studio_v2 import workspace_root

Observation = v5.Observation
TrackDraft = v5.TrackDraft
TrackRepresentative = v5.TrackRepresentative
CandidateDraft = v5.CandidateDraft

DIVERSITY_THRESHOLDS = {
    "person_reid": 0.965,
    "clothing_upper": 0.94,
    "clothing_lower": 0.94,
    "body_hist": 0.95,
    "body_structure": 0.93,
    "face": 0.955,
}


def _observation_is_clean(observation: Observation) -> bool:
    instance_class = str(getattr(observation, "instance_class", "UNKNOWN"))
    if instance_class != "UNKNOWN":
        return bool(getattr(observation, "gallery_eligible", False)) and instance_class == "CLEAN"
    return observation.interference_ratio <= v5.CLEAN_INTERFERENCE_MAX


def _quality(observation: Observation) -> float:
    feature_quality = getattr(observation, "person_feature_quality", None)
    if feature_quality is not None:
        return max(0.0, min(1.0, float(feature_quality)))
    return v5._representative_quality(observation)


def representatives_diverse(left: TrackRepresentative, right: TrackRepresentative) -> bool:
    """Keep cross-shot and genuinely different whole-person views in the gallery."""

    a = left.observation
    b = right.observation
    if a.shot_id != b.shot_id:
        # Phase C needs independent Shot support; do not let one long Shot own Gallery evidence.
        return True

    left_bundle = getattr(a, "person_feature_bundle", None)
    right_bundle = getattr(b, "person_feature_bundle", None)
    if left_bundle is None or right_bundle is None:
        return v5._representative_diverse(left, right)

    scores = feature_channel_scores(left_bundle, right_bundle)
    for channel, threshold in DIVERSITY_THRESHOLDS.items():
        score = scores.get(channel)
        if score is not None and score < threshold:
            return True
    return abs(int(a.source_time_us) - int(b.source_time_us)) >= 700_000


def select_track_representatives(track: TrackDraft) -> list[TrackRepresentative]:
    """Prefer CLEAN whole-person quality and multi-channel visual diversity."""

    scored = [
        TrackRepresentative(
            observation=item,
            quality_score=_quality(item),
            clean=_observation_is_clean(item),
        )
        for item in track.observations
        if isinstance(item, Observation)
    ]
    scored.sort(key=lambda item: (1 if item.clean else 0, item.quality_score), reverse=True)
    selected: list[TrackRepresentative] = []
    for item in scored:
        if selected and not any(representatives_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        if len(selected) >= v5.TRACK_GALLERY_LIMIT:
            break
    if not selected and scored:
        selected.append(scored[0])
    return selected


def _safe_crop(representative: TrackRepresentative):
    if not representative.clean:
        return None, None
    observation = representative.observation
    frame = v5._read_frame(observation.reference_path, observation.local_time_us)
    if frame is None:
        return None, None
    height, width = frame.shape[:2]
    safety = classify_person_instance(
        person_bbox=observation.bbox,
        other_person_boxes=list(getattr(observation, "other_person_boxes", []) or []),
        frame_width=width,
        frame_height=height,
        proposal_source=str(observation.detection_source or ""),
        force_partial="face-fallback" in str(observation.detection_source or "").lower(),
    )
    if not gallery_crop_is_valid(safety, frame_width=width, frame_height=height):
        return None, None
    x, y, w, h = safety.crop_bbox
    crop = frame[y:y + h, x:x + w]
    if crop.size == 0:
        return None, None
    return crop, safety


def _save_feature_sidecar(root, index: int, observation: Observation) -> tuple[str | None, dict[str, int]]:
    bundle = getattr(observation, "person_feature_bundle", None)
    if bundle is None:
        return None, {}

    import numpy as np

    arrays = {
        name: getattr(bundle, name)
        for name in (
            "person_reid",
            "clothing_upper",
            "clothing_lower",
            "body_hist",
            "body_structure",
            "face",
        )
        if getattr(bundle, name) is not None
    }
    if not arrays:
        return None, {}

    path = root / f"features_{index:02d}.npz"
    np.savez_compressed(
        str(path),
        **{name: np.asarray(value, dtype=np.float32) for name, value in arrays.items()},
    )
    return str(path), feature_dimensions(bundle)


def save_candidate_gallery(run_id: str, candidate: CandidateDraft, ordinal: int) -> list[str]:
    """Persist CLEAN Person crops + separate multi-channel feature sidecars."""

    import cv2

    root = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}"
    saved: list[str] = []
    manifest_images: list[dict[str, object]] = []
    for index, representative in enumerate(candidate.gallery, start=1):
        crop, safety = _safe_crop(representative)
        if crop is None or safety is None:
            continue
        path = root / f"gallery_{index:02d}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), crop):
            continue
        saved.append(str(path))
        observation = representative.observation
        feature_path, dimensions = _save_feature_sidecar(root, index, observation)
        bundle = getattr(observation, "person_feature_bundle", None)
        manifest_images.append({
            "path": str(path),
            "feature_path": feature_path,
            "feature_version": getattr(bundle, "feature_version", None),
            "feature_channels": list(getattr(bundle, "available_channels", ()) or ()),
            "feature_dimensions": dimensions,
            "shot_id": observation.shot_id,
            "source_time_us": observation.source_time_us,
            "instance_id": getattr(observation, "instance_id", None),
            "person_bbox": list(safety.person_bbox),
            "crop_bbox": list(safety.crop_bbox),
            "quality": round(representative.quality_score, 6),
            "face_visible": bool(observation.face_visible),
            "face_score": round(float(getattr(observation, "face_score", 0.0)), 6),
            "instance_class": safety.instance_class,
            "gallery_eligible": True,
            "contamination_ratio": round(safety.contamination_ratio, 6),
            "isolation": "clean-person-instance-crop",
        })

    root.mkdir(parents=True, exist_ok=True)
    (root / "gallery.json").write_text(json.dumps({
        "candidate_id": candidate.id,
        "identity_status": candidate.identity_status,
        "feature_version": FEATURE_VERSION,
        "policy": (
            "V9 Phase B: formal gallery contains CLEAN Person Instance crops only; "
            "ReID/clothing/body/face channels are preserved separately; whole frames forbidden"
        ),
        "image_count": len(manifest_images),
        "images": manifest_images,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    paths = save_candidate_gallery(run_id, candidate, ordinal)
    return paths[0] if paths else None
