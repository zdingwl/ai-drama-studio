"""人物视觉兼容入口。

正式实现已经升级到 V5：
- Shot 内先 Person Detection + Multi-Person Track；
- 每个 Track 先选高质量、单人干净代表图；
- Track Gallery vs Character Gallery 做跨 Shot 身份判断；
- 同一 Character_ID 随视频分析持续吸收新的干净代表图；
- YOLOX / YoutuReID 仍保持 GPU 优先、CPU fallback。

保存层额外经过 character_gallery_persistence_v5：正式 Gallery 与 face-only cover 都不允许带入其他人物。

保留本文件只为了让 content_analysis_v2 / 历史测试 import 路径稳定。
"""

from engine.app.character_visual_v5 import (  # noqa: F401
    CandidateDraft,
    CharacterProgress,
    IdentityStatus,
    Observation,
    TrackDraft,
    TrackRepresentative,
    analyze_characters,
    bbox_iou,
    build_tracks,
    candidate_confidence,
    cluster_candidates,
    cosine,
    detect_observations,
    mean_vector,
    sample_ratios,
    sample_times_us,
    select_track_representatives,
)
from engine.app.character_gallery_persistence_v5 import (  # noqa: F401
    save_candidate_cover,
    save_candidate_gallery,
)

__all__ = [
    "CandidateDraft",
    "CharacterProgress",
    "IdentityStatus",
    "Observation",
    "TrackDraft",
    "TrackRepresentative",
    "analyze_characters",
    "bbox_iou",
    "build_tracks",
    "candidate_confidence",
    "cluster_candidates",
    "cosine",
    "detect_observations",
    "mean_vector",
    "sample_ratios",
    "sample_times_us",
    "save_candidate_cover",
    "save_candidate_gallery",
    "select_track_representatives",
]
