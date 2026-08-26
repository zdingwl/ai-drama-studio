"""Character V9 Phase C formal runtime entry.

Person + Partial-Person Observation (12fps)
→ explicit Person Instance split and crop safety
→ multi-channel Person Image features (ReID / clothing / body / optional face)
→ Mature MOT (BoT-SORT / ByteTrack fallback)
→ CLEAN-only Person Gallery evidence
→ V9C Anchor-first Person Gallery identity
→ confirm A -> absorb all remaining -> confirm B -> absorb against A+B -> ...
→ partial/occluded/contaminated evidence may only extend confirmed identities or remain UNRESOLVED

Track count and Face count never determine Final Character count. A new Character can only be
created by a stable, multi-shot CLEAN Person Gallery that is clearly different from every already
confirmed Person Gallery.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_v9c import resolve_global_identities
from engine.app.character_observation_v9 import detect_observations
from engine.app.character_person_features_v9 import FEATURE_VERSION
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
        channels: dict[str, int] = {}
        ready_features = 0
        for item in observations:
            key = str(getattr(item, "instance_class", "UNKNOWN"))
            classes[key] = classes.get(key, 0) + 1
            bundle = getattr(item, "person_feature_bundle", None)
            if bundle is None:
                continue
            ready_features += 1
            for channel in bundle.available_channels:
                channels[channel] = channels.get(channel, 0) + 1
        logger.warning(
            "[CharacterV9C] observations=%s feature_ready=%s tracks=%s confirmed_galleries=%s "
            "unresolved_evidence=%s instance_classes=%s feature_channels=%s",
            len(observations),
            ready_features,
            len(tracks),
            len(resolved),
            len(unresolved),
            classes,
            channels,
        )
        for index, candidate in enumerate(resolved, start=1):
            metadata = dict(getattr(candidate, "v9_metadata", {}) or {})
            logger.warning(
                "[CharacterV9C] gallery=%s images=%s shots=%s face_images=%s tracks=%s bound_shots=%s",
                index,
                metadata.get("confirmed_gallery_images"),
                metadata.get("confirmed_gallery_shots"),
                metadata.get("face_images"),
                len(candidate.tracks),
                len({track.shot_id for track in candidate.tracks}),
            )
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V9 Phase C 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX/ReID CUDA 不可用可以 CPU fallback，但 trackers/supervision 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v9c-person-gallery-anchor-first",
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
        "features": {
            "version": FEATURE_VERSION,
            "unit": "isolated Person Instance image",
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
            "formal_representatives": "CLEAN Person Instance crops only",
            "quality_basis": "whole-person quality; face prominence is not required",
            "feature_sidecar": "compressed NPZ per gallery image",
            "occluded_contaminated_partial": "may extend confirmed gallery only; never seed a Character",
            "whole_frame_gallery_image": False,
        },
        "identity": {
            "resolver": "V9C Person Gallery Anchor-first Confirm-then-Absorb",
            "comparison_order": "all remaining images compare to every confirmed gallery before any new gallery may be created",
            "outcomes": ["MATCH", "AMBIGUOUS", "DIFFERENT"],
            "ambiguous_policy": "UNRESOLVED; cannot seed duplicate Character",
            "new_identity_gate": "3+ independent CLEAN Person Gallery shots + multichannel consistency + clear novelty",
            "face_role": "optional supporting channel; never sole identity definition",
            "track_role": "presence/evidence only; never identity cardinality",
            "v8_identity": "DISABLED",
        },
    }
