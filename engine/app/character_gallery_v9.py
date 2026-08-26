"""Character V9 Phase A gallery safety.

Only CLEAN Person Instance crops can enter a formal person gallery. Dirty/partial
observations remain Track Evidence and may still be used later for conservative
presence attachment, but never become gallery representatives or covers.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.app import character_visual_v5 as v5
from engine.app.character_person_instance_v9 import classify_person_instance, gallery_crop_is_valid
from engine.app.studio_v2 import workspace_root

Observation = v5.Observation
TrackDraft = v5.TrackDraft
TrackRepresentative = v5.TrackRepresentative
CandidateDraft = v5.CandidateDraft


def _observation_is_clean(observation: Observation) -> bool:
    instance_class = str(getattr(observation, "instance_class", "UNKNOWN"))
    if instance_class != "UNKNOWN":
        return bool(getattr(observation, "gallery_eligible", False)) and instance_class == "CLEAN"
    return observation.interference_ratio <= v5.CLEAN_INTERFERENCE_MAX


def select_track_representatives(track: TrackDraft) -> list[TrackRepresentative]:
    scored = [
        TrackRepresentative(
            observation=item,
            quality_score=v5._representative_quality(item),
            clean=_observation_is_clean(item),
        )
        for item in track.observations
        if isinstance(item, Observation)
    ]
    scored.sort(key=lambda item: (1 if item.clean else 0, item.quality_score), reverse=True)
    selected: list[TrackRepresentative] = []
    for item in scored:
        if selected and not any(v5._representative_diverse(item, existing) for existing in selected):
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


def save_candidate_gallery(run_id: str, candidate: CandidateDraft, ordinal: int) -> list[str]:
    """Persist only explicit CLEAN Person Instance crops; never save a whole frame."""

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
        manifest_images.append({
            "path": str(path),
            "shot_id": observation.shot_id,
            "source_time_us": observation.source_time_us,
            "instance_id": getattr(observation, "instance_id", None),
            "person_bbox": list(safety.person_bbox),
            "crop_bbox": list(safety.crop_bbox),
            "quality": round(representative.quality_score, 6),
            "face_visible": bool(observation.face_visible),
            "instance_class": safety.instance_class,
            "gallery_eligible": True,
            "contamination_ratio": round(safety.contamination_ratio, 6),
            "isolation": "clean-person-instance-crop",
        })

    root.mkdir(parents=True, exist_ok=True)
    (root / "gallery.json").write_text(json.dumps({
        "candidate_id": candidate.id,
        "identity_status": candidate.identity_status,
        "policy": "V9 Phase A: formal gallery contains CLEAN Person Instance crops only; whole frames forbidden",
        "image_count": len(manifest_images),
        "images": manifest_images,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    paths = save_candidate_gallery(run_id, candidate, ordinal)
    return paths[0] if paths else None
