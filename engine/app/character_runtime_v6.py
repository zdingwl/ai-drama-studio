"""Character V8 formal runtime entry.

Person + Partial-Person Observation (12fps)
→ Geometry-safe Face Ownership
→ Mature MOT (BoT-SORT / ByteTrack fallback)
→ Anchor-first / Confirm-then-Absorb Identity
→ confirmed Identity Gallery absorbs later Face Evidence first
→ only clearly novel, cross-shot-supported Face may create next Identity
→ Body/Partial attaches after identity exists or remains UNRESOLVED
→ RESOLVED / UNRESOLVED Candidate

Hard product rule: first confirm a person, then compare all later evidence against confirmed people before creating another person.
Track count can never determine Final Character count.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_v8 import resolve_global_identities
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
            "[CharacterV8] observations=%s tracks=%s confirmed_identities=%s unresolved_evidence=%s",
            len(observations),
            len(tracks),
            len(resolved),
            len(unresolved),
        )
        for index, candidate in enumerate(resolved, start=1):
            metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
            logger.warning(
                "[CharacterV8] identity=%s seed_face=%.4f seed_quality=%.4f face_shots=%s face_anchors=%s tracks=%s shots=%s",
                index,
                float(metadata.get("seed_face_score") or 0.0),
                float(metadata.get("seed_quality") or 0.0),
                metadata.get("face_shot_count"),
                metadata.get("face_anchor_count"),
                len(candidate.tracks),
                len({track.shot_id for track in candidate.tracks}),
            )
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V8 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX/ReID CUDA 不可用可以 CPU fallback，但 trackers/supervision 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v8-anchor-first-confirm-then-absorb",
        "observation": {
            "sample_fps": 12.0,
            "normal_person_threshold": 0.32,
            "partial_person_proposal_threshold": 0.10,
            "face_ownership": "global one-to-one geometry gate; partial cannot own face",
        },
        "tracking": tracker_runtime_status(),
        "identity": {
            "resolver": "Anchor-first Confirm-then-Absorb",
            "identity_creation": "highest-quality Face seed + cross-shot confirmation",
            "comparison_order": "every remaining Face compares against all confirmed identities before any new identity may be created",
            "ambiguity_policy": "similar but uncertain -> UNRESOLVED, never duplicate Final Character",
            "novelty_policy": "new identity requires cross-shot support and clear novelty against all confirmed identities",
            "body_partial_policy": "attach after identity exists or remain UNRESOLVED; never create identity",
            "final_gate": "confirmed identities only",
            "face_provider": "YuNet + SFace (replaceable provider)",
        },
    }
