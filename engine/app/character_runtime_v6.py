"""Character V10 formal runtime entry.

Person / Partial-Person Observation (12fps)
→ split every detected person into an explicit Person Instance
→ extract isolated-person model features
→ capture every model-usable front/side/back/occluded/multi-person-frame crop
→ persist pre-classification Person Evidence when a Run id is available
→ Mature MOT + evidence-only singleton fallback
→ classify captured Person Evidence with YoutuReID person model against full identity galleries
→ write A/B/C identity assignments back to the captured evidence manifest
→ persist multi-view classified Person Gallery
→ Final Character is identity class cardinality, never Track/Face count.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_evidence_store_v10 import save_person_evidence, update_person_evidence_classification
from engine.app.character_identity_v10 import CLASSIFIER_MODEL, RESOLVER_VERSION, resolve_global_identities
from engine.app.character_observation_v10 import detect_observations
from engine.app.character_person_features_v9 import FEATURE_VERSION
from engine.app.character_tracking_v10 import build_tracks, tracker_runtime_status
from engine.app.content_models_v2 import RequiredCharacterModelError

logger = logging.getLogger(__name__)

FORMAL_IDENTITY_EVIDENCE = "Character V10 capture-first Person Evidence + model classification"
FORMAL_IDENTITY_PROFILE = "f05-assets-v10-person-evidence-model-classification"


def _bridge_persistence_metadata(candidates: list[v5.CandidateDraft]) -> None:
    for candidate in candidates:
        metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
        candidate.v6_metadata = {  # type: ignore[attr-defined]
            "identity": FORMAL_IDENTITY_EVIDENCE,
            "profile": FORMAL_IDENTITY_PROFILE,
            "identity_policy": (
                "capture every model-usable Person Instance first; classify with Person ReID model; "
                "front/side/back and multi-person-frame crops are valid evidence; Face optional"
            ),
            **metadata,
        }


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: v5.CharacterProgress | None = None,
    *,
    run_id: str | None = None,
) -> list[v5.CandidateDraft]:
    try:
        observations = detect_observations(shots, progress=progress)
        evidence_store: dict[str, Any] | None = None
        if run_id:
            evidence_store = save_person_evidence(run_id, observations)
        tracks = build_tracks(observations)
        candidates = resolve_global_identities(tracks)
        classification_store: dict[str, int] | None = None
        if run_id and evidence_store is not None:
            classification_store = update_person_evidence_classification(run_id, candidates)
        _bridge_persistence_metadata(candidates)
        resolved = [item for item in candidates if item.identity_status == "RESOLVED"]
        unresolved = [item for item in candidates if item.identity_status != "RESOLVED"]

        classes: dict[str, int] = {}
        captured = 0
        seedable = 0
        for item in observations:
            key = str(getattr(item, "instance_class", "UNKNOWN"))
            classes[key] = classes.get(key, 0) + 1
            if bool(getattr(item, "person_evidence_eligible", False)):
                captured += 1
            if bool(getattr(item, "person_seed_eligible", False)):
                seedable += 1

        logger.warning(
            "[CharacterV10] observations=%s captured_person_evidence=%s persisted_person_evidence=%s classified_persisted=%s "
            "seedable=%s tracks=%s confirmed_identities=%s unresolved_fragments=%s instance_classes=%s",
            len(observations), captured,
            (evidence_store or {}).get("evidence_count") if evidence_store else None,
            (classification_store or {}).get("classified_count") if classification_store else None,
            seedable, len(tracks), len(resolved), len(unresolved), classes,
        )
        for index, candidate in enumerate(resolved, start=1):
            metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
            logger.warning(
                "[CharacterV10] identity=%s classified_gallery_images=%s confirmed_seed_images=%s "
                "confirmed_seed_shots=%s classified_shots=%s classes=%s tracks=%s",
                index,
                metadata.get("captured_classified_images"),
                metadata.get("confirmed_gallery_images"),
                metadata.get("confirmed_gallery_shots"),
                metadata.get("classified_shots"),
                metadata.get("instance_classes"),
                len(candidate.tracks),
            )
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V10 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX / YoutuReID 可 CPU fallback，但 Mature MOT 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v10-capture-first-model-classification",
        "observation": {
            "sample_fps": 12.0,
            "person_instance": "one detected person -> one explicit person crop, including multi-person frames",
            "capture_first": True,
            "preclassification_persistence": True,
            "classification_written_back": True,
            "identity_before_capture_filter": False,
            "crop_classes": ["CLEAN", "OCCLUDED", "CONTAMINATED", "PARTIAL"],
            "front_side_back_supported": True,
            "whole_frame_identity_input": False,
            "same_sample_cannot_link": True,
        },
        "features": {
            "version": FEATURE_VERSION,
            "unit": "isolated Person Instance image",
            "primary_model": "YoutuReID Person Re-identification",
            "channels": [
                "person_reid",
                "clothing_upper",
                "clothing_lower",
                "body_hist",
                "body_structure",
                "face(optional)",
            ],
            "single_total_embedding": False,
            "demographic_inference": False,
            "whole_frame_feature": False,
        },
        "tracking": tracker_runtime_status(),
        "gallery": {
            "formal_representatives": "classified model-usable Person Instance crops; CLEAN is not required",
            "views": "front / side / back / occluded / person split from multi-person frame",
            "feature_sidecar": "compressed NPZ per gallery image",
            "preclassification_store": "analysis/<run_id>/person_evidence",
            "whole_frame_gallery_image": False,
        },
        "identity": {
            "resolver": RESOLVER_VERSION,
            "classifier_model": CLASSIFIER_MODEL,
            "workflow": "capture Person Evidence -> persist -> model compare -> classify A/B/C -> write assignment back -> persist classified galleries",
            "person_reid_role": "primary model signal for viewpoint-invariant person comparison",
            "clothing_body_role": "supporting channels",
            "face_role": "optional support; never required",
            "track_role": "temporal organization only; never identity cardinality",
            "partial_policy": "save/classify/attach with stronger support; cannot seed new identity",
        },
    }
