"""人物视觉兼容入口。

正式实现已经升级到 V4.1 GPU-first：
- 业务数据结构 / Track / Identity Clustering 继续复用 :mod:`engine.app.character_visual_v4`；
- YOLOX Person Detection + YoutuReID 通过 :mod:`engine.app.character_visual_gpu_v41`
  默认优先 ONNX Runtime CUDA，CUDA 不可用时自动 CPU fallback。

保留本文件只为了让现有 content_analysis_v2 / 历史测试的 import 路径保持稳定。
"""

from engine.app.character_visual_v4 import (  # noqa: F401
    CandidateDraft,
    CharacterProgress,
    IdentityStatus,
    Observation,
    TrackDraft,
    bbox_iou,
    build_tracks,
    candidate_confidence,
    cluster_candidates,
    cosine,
    mean_vector,
    sample_ratios,
    save_candidate_cover,
)
from engine.app.character_visual_gpu_v41 import (  # noqa: F401
    analyze_characters,
    detect_observations,
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
