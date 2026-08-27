"""Character V10.1 formal runtime entry.

Person / Partial-Person Observation (12fps)
→ split every detected person into an explicit Person Instance
→ extract isolated-person model features
→ capture every model-usable front/side/back/occluded/multi-person-frame crop
→ persist pre-classification Person Evidence when a Run id is available
→ Mature MOT + evidence-only singleton fallback
→ classify captured Person Evidence with YoutuReID person model against full identity galleries
→ allow strong contaminated / substantial partial views to form a new identity only
  after strict cross-shot model confirmation
→ independently assign already-confirmed identities to every Shot from all original
  Track/Observation evidence, without moving Track ownership
→ write A/B/C identity assignments back to the captured evidence manifest
→ persist multi-view classified Person Gallery + explicit Shot presence metadata
→ Final Character is identity class cardinality; Final Shot binding consumes explicit
  Shot presence assignments rather than inferring presence from candidate Track ownership.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_evidence_store_v10 import save_person_evidence, update_person_evidence_classification
from engine.app.character_identity_v101 import CLASSIFIER_MODEL, RESOLVER_VERSION, resolve_global_identities
from engine.app.character_observation_v10 import detect_observations
from engine.app.character_person_features_v9 import FEATURE_VERSION
from engine.app.character_shot_assignment_v101 import assign_shot_characters
from engine.app.character_tracking_v10 import build_tracks, tracker_runtime_status
from engine.app.content_models_v2 import RequiredCharacterModelError

logger = logging.getLogger(__name__)

FORMAL_IDENTITY_EVIDENCE = "Character V10.1 capture-first Person Evidence + strict cross-shot model classification"
FORMAL_IDENTITY_PROFILE = "f05-assets-v10.1-person-evidence-model-classification"


def _bridge_persistence_metadata(candidates: list[v5.CandidateDraft]) -> None:
    for candidate in candidates:
        metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
        candidate.v6_metadata = {  # type: ignore[attr-defined]
            "identity": FORMAL_IDENTITY_EVIDENCE,
            "profile": FORMAL_IDENTITY_PROFILE,
            "identity_policy": (
                "capture every model-usable Person Instance first; classify with Person ReID model; "
                "front/side/back and multi-person-frame crops are valid evidence; Face optional; "
                "strong contaminated/substantial partial views require stricter multi-shot confirmation; "
                "Shot presence is independently assigned from all original Track/Observation evidence "
                "after project identities are confirmed"
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
        candidates = assign_shot_characters(tracks, candidates)
        classification_store: dict[str, int] | None = None
        if run_id and evidence_store is not None:
            classification_store = update_person_evidence_classification(run_id, candidates)
        _bridge_persistence_metadata(candidates)
        resolved = [item for item in candidates if item.identity_status == "RESOLVED"]
        unresolved = [item for item in candidates if item.identity_status != "RESOLVED"]
        shot_assignments = sum(
            int((getattr(item, "v10_metadata", {}) or {}).get("shot_presence_count") or 0)
            for item in resolved
        )
        recovered_shot_assignments = sum(
            int((getattr(item, "v10_metadata", {}) or {}).get("shot_presence_recovered_count") or 0)
            for item in resolved
        )

        classes: dict[str, int] = {}
        seedable_classes: dict[str, int] = {}
        captured = 0
        seedable = 0
        for item in observations:
            key = str(getattr(item, "instance_class", "UNKNOWN"))
            classes[key] = classes.get(key, 0) + 1
            if bool(getattr(item, "person_evidence_eligible", False)):
                captured += 1
            if bool(getattr(item, "person_seed_eligible", False)):
                seedable += 1
                seedable_classes[key] = seedable_classes.get(key, 0) + 1

        logger.warning(
            "[CharacterV10.1] observations=%s captured_person_evidence=%s persisted_person_evidence=%s classified_persisted=%s "
            "seedable=%s seedable_classes=%s tracks=%s confirmed_identities=%s shot_assignments=%s "
            "recovered_shot_assignments=%s unresolved_fragments=%s instance_classes=%s",
            len(observations), captured,
            (evidence_store or {}).get("evidence_count") if evidence_store else None,
            (classification_store or {}).get("classified_count") if classification_store else None,
            seedable, seedable_classes, len(tracks), len(resolved), shot_assignments,
            recovered_shot_assignments, len(unresolved), classes,
        )
        for index, candidate in enumerate(resolved, start=1):
            metadata = dict(getattr(candidate, "v10_metadata", {}) or {})
            logger.warning(
                "[CharacterV10.1] identity=%s classified_gallery_images=%s confirmed_seed_images=%s "
                "confirmed_seed_shots=%s classified_shots=%s classes=%s seed_classes=%s risky_seed=%s "
                "shot_presence=%s shot_presence_recovered=%s presence_shots=%s tracks=%s",
                index,
                metadata.get("captured_classified_images"),
                metadata.get("confirmed_gallery_images"),
                metadata.get("confirmed_gallery_shots"),
                metadata.get("classified_shots"),
                metadata.get("instance_classes"),
                metadata.get("seed_instance_classes"),
                metadata.get("risky_seed_confirmation"),
                metadata.get("shot_presence_count"),
                metadata.get("shot_presence_recovered_count"),
                metadata.get("shot_presence_shot_ids"),
                len(candidate.tracks),
            )
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V10.1 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX / YoutuReID 可 CPU fallback，但 Mature MOT 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v10.1-capture-first-model-classification",
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
            "workflow": (
                "capture Person Evidence -> persist -> model compare -> classify A/B/C -> "
                "independent Shot x known-Character assignment -> write identity assignment back -> persist classified galleries"
            ),
            "person_reid_role": "primary model signal for viewpoint-invariant person comparison",
            "clothing_body_role": "supporting channels",
            "face_role": "optional support; strong high-quality Face may confirm known-Character Shot presence but is never required",
            "track_role": "temporal organization only; Track ownership is not the Final Shot-binding source",
            "risky_seed_policy": "strong contaminated/substantial partial person images may seed only after stricter >=3-shot Person-ReID confirmation",
            "weak_partial_policy": "save/classify only; cannot seed new identity",
            "shot_binding": (
                "after identities are confirmed, score every Shot independently against all known Character galleries using "
                "Face/ReID/appearance + temporal repetition + current-Shot cannot-link constraints; Final binding consumes "
                "explicit Shot-presence assignments and never depends on moving unresolved Tracks into a Character"
            ),
        },
    }
