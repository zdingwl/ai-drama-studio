"""Character V6.1 正式运行入口。

Person + Partial-Person Observation (12fps)
→ Mature MOT (BoT-SORT / ByteTrack fallback)
→ Partial Track temporal confirmation
→ Clean Track Gallery
→ Global Identity Graph
→ RESOLVED / UNRESOLVED Candidate

重要边界：partial/body-only 必须能够表达“这里有人”，但不能独立创建 Final Character；
UNRESOLVED 只保留 Evidence，Final Asset 层继续使用 RESOLVED-only allow-list。
"""
from __future__ import annotations

from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_v6 import resolve_global_identities
from engine.app.character_observation_v6 import detect_observations
from engine.app.character_tracking_v6 import build_tracks, tracker_runtime_status
from engine.app.content_models_v2 import RequiredCharacterModelError


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: v5.CharacterProgress | None = None,
) -> list[v5.CandidateDraft]:
    try:
        observations = detect_observations(shots, progress=progress)
        tracks = build_tracks(observations)
        return resolve_global_identities(tracks)
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V6.1 运行时未准备完整。请重新安装 engine/requirements.txt 后重启后端；"
            "YOLOX/ReID CUDA 不可用可以 CPU fallback，但 trackers/supervision 运行时缺失不能发布人物结果。"
        ) from exc


def runtime_status() -> dict[str, object]:
    return {
        "profile": "character-v6.1-partial-person-global-identity",
        "observation": {
            "sample_fps": 12.0,
            "normal_person_threshold": 0.32,
            "partial_person_proposal_threshold": 0.10,
            "partial_policy": "temporal confirmation before Evidence; never direct Final Character",
        },
        "tracking": tracker_runtime_status(),
        "identity": {
            "resolver": "Global Identity Graph",
            "final_gate": "RESOLVED only",
            "unresolved_policy": "Evidence only; never auto materialize Final Character",
            "face_provider": "YuNet + SFace (replaceable provider)",
        },
    }
