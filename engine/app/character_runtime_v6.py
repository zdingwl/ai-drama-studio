"""Character V9 Phase A formal runtime entry.

Phase A scope only:
Person + Partial-Person Observation (12fps)
→ one explicit Person Instance per detected person
→ CLEAN / OCCLUDED / CONTAMINATED / PARTIAL classification
→ explicit single-person crop bbox + same-sample cannot-link metadata
→ Mature MOT (BoT-SORT / ByteTrack fallback)
→ CLEAN-only gallery representatives
→ existing V8 Anchor-first identity decisions through a V9 clean-gallery adapter

Hard product rule for this phase: whole frames must never become person gallery images.
Multi-person frames are split before tracking/identity and dirty crops never seed a gallery.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_v9a import resolve_global_identities
from engine.app.character_observation_v9 import detect_observations
from engine.app.character_tracking_v9 import build_tracks, tracker_runtime_status
from engine.app.content_models_v2 import RequiredCharacterModelError

logger = logging.getLogger(__name__)


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: v5.CharacterProgress | None = None,
) -> list[v5.CandidateDraft]:
    try:
        observations = detect_observations(shots, progress=progress)
        tracks = build_tracks(observations)
        candidates = resolve_global_identities(tracks)
        resolved = [item for item in candidates if item.identity_status == "RESOLVED"]
        unresolved = [item for item in candidates if item.identity_status != "RESOLVED"]
        classes: dict[str, int] = {}
        for item in observations:
            key = str(getattr(item, "instance_class", "UNKNOWN"))
            classes[key] = classes.get(key, 0) + 1
        logger.warning(
            "[CharacterV9A] observations=%s tracks=%s confirmed_identities=%s unresolved_evidence=%s instance_classes=%s",
            len(observations),
            len(tracks),
            len(resolved),
            len(unresolved),
            classes,
        )
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V9 Phase A 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX/ReID CUDA 不可用可以 CPU fallback，但 trackers/supervision 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v9a-person-instance-safety-v8-identity",
        "observation": {
            "sample_fps": 12.0,
            "normal_person_threshold": 0.32,
            "partial_person_proposal_threshold": 0.10,
            "person_instance": "one detected person -> one explicit instance/crop",
            "crop_classes": ["CLEAN", "OCCLUDED", "CONTAMINATED", "PARTIAL"],
            "whole_frame_identity_input": False,
            "same_sample_cannot_link": True,
            "face_ownership": "global one-to-one geometry gate; partial cannot own face",
        },
        "tracking": tracker_runtime_status(),
        "gallery": {
            "formal_representatives": "CLEAN Person Instance crops only",
            "occluded_contaminated_partial": "Evidence only; forbidden as gallery seed/cover",
            "whole_frame_gallery_image": False,
            "post_identity_rebuild": True,
        },
        "identity": {
            "resolver": "V8 Anchor-first decisions via V9A clean-gallery adapter",
            "v9_person_gallery_identity": "NOT_YET_ENABLED",
        },
    }
