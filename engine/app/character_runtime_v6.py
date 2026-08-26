"""Character V7 formal runtime entry.

Person + Partial-Person Observation (12fps)
→ Geometry-safe Face Ownership
→ Mature MOT (BoT-SORT / ByteTrack fallback)
→ Face observations become the ONLY identity nodes
→ Face-first Global Identity Graph
→ Person/partial/body Tracks attach after identity exists
→ RESOLVED / UNRESOLVED Candidate

Hard product rule: Track count must never determine Final Character count.
Only stable Face Identity clusters can create Final Characters; partial/body-only Evidence can attach or remain UNRESOLVED.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_v7 import resolve_global_identities
from engine.app.character_observation_v63 import detect_observations
from engine.app.character_tracking_v6 import build_tracks, tracker_runtime_status
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
        logger.warning(
            "[CharacterV7] observations=%s tracks=%s resolved_face_identities=%s unresolved_evidence=%s",
            len(observations),
            len(tracks),
            len(resolved),
            len(unresolved),
        )
        for index, candidate in enumerate(resolved, start=1):
            metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
            logger.warning(
                "[CharacterV7] identity=%s face_shots=%s face_anchors=%s tracks=%s shots=%s",
                index,
                metadata.get("face_shot_count"),
                metadata.get("face_anchor_count"),
                len(candidate.tracks),
                len({track.shot_id for track in candidate.tracks}),
            )
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V7 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX/ReID CUDA 不可用可以 CPU fallback，但 trackers/supervision 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v7-face-first-global-identity",
        "observation": {
            "sample_fps": 12.0,
            "normal_person_threshold": 0.32,
            "partial_person_proposal_threshold": 0.10,
            "face_ownership": "global one-to-one geometry gate; partial cannot own face",
        },
        "tracking": tracker_runtime_status(),
        "identity": {
            "resolver": "Face-first Global Identity Graph",
            "identity_node": "high-quality Face observation, never Person Track",
            "final_character_count_source": "stable Face Identity clusters only",
            "default_resolution_gate": ">=3 distinct Face shots",
            "two_shot_exception": "only very strong Face/ReID evidence",
            "body_partial_policy": "attach after identity exists or remain UNRESOLVED",
            "final_gate": "RESOLVED only",
            "face_provider": "YuNet + SFace (replaceable provider)",
        },
    }
