"""Character V5.1 runtime 安全门槛。

职责：
- CUDA Provider 不可用：允许 ONNX Runtime CPUExecutionProvider fallback；
- onnxruntime 整体未安装/损坏：本次 V5.1 Run 必须失败并保留旧 Current；
- Shot 内 Track 经过 Face hard-conflict 防串轨；
- 跨 Shot 身份经过 Conservative Identity：Face 有否决权，Body ReID 只能辅助；
- 禁止把“运行时缺失”误解释成“没有人物”。
"""
from __future__ import annotations

from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_identity_policy_v51 import cluster_candidates
from engine.app.character_track_policy_v51 import build_tracks
from engine.app.content_models_v2 import RequiredCharacterModelError


def detect_observations(shots: list[dict[str, Any]], progress: v5.CharacterProgress | None = None) -> list[v5.Observation]:
    try:
        return v5.detect_observations(shots, progress=progress)
    except (ImportError, ModuleNotFoundError) as exc:
        raise RequiredCharacterModelError(
            "人物识别 V5.1 ONNX Runtime 未准备完整。请安装 engine/requirements.txt 后重启后端；"
            "CUDA Provider 不可用会自动 CPU fallback，但运行时本身缺失不能发布空人物结果。"
        ) from exc


def analyze_characters(shots: list[dict[str, Any]], progress: v5.CharacterProgress | None = None) -> list[v5.CandidateDraft]:
    observations = detect_observations(shots, progress=progress)
    tracks = build_tracks(observations)
    return cluster_candidates(tracks)
