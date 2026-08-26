"""Character V6.3 正式运行入口。

Person + Partial-Person Observation (12fps)
→ Geometry-safe Face Ownership
→ Mature MOT (BoT-SORT / ByteTrack fallback)
→ Partial Track temporal confirmation
→ Clean Track Gallery
→ Spatiotemporal Global Identity Graph
→ Conservative resolved-fragment consolidation
→ Identity pair diagnostics
→ RESOLVED / UNRESOLVED Candidate

重要边界：partial/body-only 必须能够表达“这里有人”，但不能独立创建 Final Character；
Face 必须先安全归属到具体 Person；同 Shot 只有真正同时且空间不同的人才 cannot-link。
"""
from __future__ import annotations

from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_diagnostics_v63 import annotate_and_log
from engine.app.character_identity_v63 import resolve_global_identities
from engine.app.character_observation_v63 import detect_observations
from engine.app.character_tracking_v6 import build_tracks, tracker_runtime_status
from engine.app.content_models_v2 import RequiredCharacterModelError


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: v5.CharacterProgress | None = None,
) -> list[v5.CandidateDraft]:
    try:
        observations = detect_observations(shots, progress=progress)
        tracks = build_tracks(observations)
        candidates = resolve_global_identities(tracks)
        annotate_and_log(candidates)
        return candidates
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V6.3 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX/ReID CUDA 不可用可以 CPU fallback，但 trackers/supervision 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v6.3-safe-face-spatiotemporal-identity",
        "observation": {
            "sample_fps": 12.0,
            "normal_person_threshold": 0.32,
            "partial_person_proposal_threshold": 0.10,
            "face_ownership": "global one-to-one geometry gate; partial cannot own face",
            "partial_policy": "temporal confirmation; can attach but never create identity anchor",
        },
        "tracking": tracker_runtime_status(),
        "identity": {
            "resolver": "Spatiotemporal Global Identity Graph + fragment consolidation",
            "same_shot_policy": "cannot-link only when temporally simultaneous and spatially distinct",
            "duplicate_track_policy": "strong Face/ReID + high bbox IoU may merge simultaneous duplicate tracks",
            "diagnostics": "resolved pair Face/ReID/shared-shot/conflict saved in candidate evidence and backend log",
            "partial_face_anchor": False,
            "final_gate": "RESOLVED only",
            "unresolved_policy": "Evidence only; never auto materialize Final Character",
            "face_provider": "YuNet + SFace (replaceable provider)",
        },
    }
