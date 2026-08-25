"""人物视觉兼容入口。

正式实现已经升级到 :mod:`engine.app.character_visual_v4`。
保留本文件只为了让现有 content_analysis_v2 / 历史测试的 import 路径不发生无意义的大迁移；
所有人物检测、Track、ReID、聚类逻辑都只维护 V4 一份。
"""

from engine.app.character_visual_v4 import (  # noqa: F401
    CandidateDraft,
    CharacterProgress,
    IdentityStatus,
    Observation,
    TrackDraft,
    analyze_characters,
    bbox_iou,
    build_tracks,
    candidate_confidence,
    cluster_candidates,
    cosine,
    detect_observations,
    mean_vector,
    sample_ratios,
    save_candidate_cover,
)

__all__ = [
    "CandidateDraft",
    "CharacterProgress",
    "IdentityStatus",
    "Observation",
    "TrackDraft",
    "analyze_characters",
    "bbox_iou",
    "build_tracks",
    "candidate_confidence",
    "cluster_candidates",
    "cosine",
    "detect_observations",
    "mean_vector",
    "sample_ratios",
    "save_candidate_cover",
]
