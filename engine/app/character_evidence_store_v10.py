"""Character V10 pre-classification Person Evidence store.

Every model-usable Person Instance crop is persisted before identity classification.
After model classification the same manifest is updated with the resulting identity
assignment, so capture and classification remain separate stages over the same data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import observation_policy
from engine.app.character_person_features_v9 import feature_dimensions
from engine.app.studio_v2 import workspace_root

JPEG_QUALITY = 88


def _root(run_id: str) -> Path:
    return workspace_root() / "analysis" / run_id / "person_evidence"


def _crop(observation: Any):
    frame = v5._read_frame(observation.reference_path, observation.local_time_us)
    if frame is None:
        return None, None
    height, width = frame.shape[:2]
    x, y, w, h = tuple(int(value) for value in getattr(observation, "person_crop_bbox", observation.bbox))
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    right = max(x + 1, min(width, x + max(1, w)))
    bottom = max(y + 1, min(height, y + max(1, h)))
    crop = frame[y:bottom, x:right]
    if crop.size == 0:
        return None, None
    return crop, (x, y, right - x, bottom - y)


def _save_features(root: Path, stem: str, observation: Any) -> tuple[str | None, dict[str, int]]:
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
    path = root / f"{stem}.npz"
    np.savez_compressed(str(path), **{name: np.asarray(value, dtype=np.float32) for name, value in arrays.items()})
    return str(path), feature_dimensions(bundle)


def save_person_evidence(run_id: str, observations: list[Any]) -> dict[str, Any]:
    import cv2

    root = _root(run_id)
    root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    counters: dict[str, int] = {}

    for observation in sorted(observations, key=lambda item: (
        str(item.episode_id), int(item.shot_ordinal), int(item.source_time_us), str(getattr(item, "instance_id", ""))
    )):
        policy = observation_policy(observation)
        if not policy.evidence_eligible:
            continue
        crop, crop_bbox = _crop(observation)
        if crop is None or crop_bbox is None:
            continue

        shot_key = str(observation.shot_id)
        counters[shot_key] = counters.get(shot_key, 0) + 1
        ordinal = counters[shot_key]
        safe_shot = shot_key.replace("/", "_").replace("\\", "_")
        stem = f"{safe_shot}_{int(observation.source_time_us):012d}_{ordinal:02d}"
        image_path = root / f"{stem}.jpg"
        if not cv2.imwrite(str(image_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]):
            continue
        feature_path, dimensions = _save_features(root, stem, observation)
        bundle = getattr(observation, "person_feature_bundle", None)
        records.append({
            "instance_id": getattr(observation, "instance_id", None),
            "shot_id": observation.shot_id,
            "episode_id": observation.episode_id,
            "shot_ordinal": int(observation.shot_ordinal),
            "source_time_us": int(observation.source_time_us),
            "image_path": str(image_path),
            "feature_path": feature_path,
            "feature_channels": list(getattr(bundle, "available_channels", ()) or ()),
            "feature_dimensions": dimensions,
            "person_bbox": list(getattr(observation, "person_bbox", observation.bbox)),
            "crop_bbox": list(crop_bbox),
            "instance_class": str(getattr(observation, "instance_class", "UNKNOWN")),
            "quality": round(float(getattr(observation, "person_feature_quality", 0.0)), 6),
            "reliability": round(policy.reliability, 6),
            "seed_eligible": policy.seed_eligible,
            "cannot_link_instance_ids": list(getattr(observation, "cannot_link_instance_ids", []) or []),
            "face_visible": bool(observation.face_visible),
            "detection_source": str(observation.detection_source or ""),
            "classification_status": "UNCLASSIFIED",
            "identity_ordinal": None,
            "candidate_id": None,
        })

    manifest = {
        "run_id": run_id,
        "policy": "capture model-usable Person Instance crops before identity classification",
        "whole_frame_identity_input": False,
        "evidence_count": len(records),
        "classified_count": 0,
        "resolved_count": 0,
        "unresolved_count": 0,
        "records": records,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"root": str(root), "evidence_count": len(records), "manifest": str(manifest_path)}


def update_person_evidence_classification(run_id: str, candidates: list[Any]) -> dict[str, int]:
    """Write model identity assignments back to the pre-classification manifest."""

    path = _root(run_id) / "manifest.json"
    if not path.exists():
        return {"classified_count": 0, "resolved_count": 0, "unresolved_count": 0}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"classified_count": 0, "resolved_count": 0, "unresolved_count": 0}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
        return {"classified_count": 0, "resolved_count": 0, "unresolved_count": 0}

    assignments: dict[str, dict[str, Any]] = {}
    resolved_ordinal = 0
    for candidate in candidates:
        status = str(getattr(candidate, "identity_status", "UNRESOLVED") or "UNRESOLVED").upper()
        identity_ordinal: int | None = None
        if status == "RESOLVED":
            resolved_ordinal += 1
            identity_ordinal = resolved_ordinal
        for track in getattr(candidate, "tracks", []) or []:
            for observation in getattr(track, "observations", []) or []:
                instance_id = getattr(observation, "instance_id", None)
                if not instance_id:
                    continue
                assignments[str(instance_id)] = {
                    "classification_status": status,
                    "identity_ordinal": identity_ordinal,
                    "candidate_id": str(getattr(candidate, "id", "")) or None,
                }

    classified = resolved = unresolved = 0
    for record in manifest["records"]:
        if not isinstance(record, dict):
            continue
        assignment = assignments.get(str(record.get("instance_id") or ""))
        if assignment is None:
            continue
        record.update(assignment)
        classified += 1
        if assignment["classification_status"] == "RESOLVED":
            resolved += 1
        else:
            unresolved += 1

    manifest["classified_count"] = classified
    manifest["resolved_count"] = resolved
    manifest["unresolved_count"] = unresolved
    manifest["classification_policy"] = "YoutuReID primary person-model classification over captured Person Evidence"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"classified_count": classified, "resolved_count": resolved, "unresolved_count": unresolved}
