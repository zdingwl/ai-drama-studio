"""人物视觉兼容入口。

正式实现已经升级到 V5.1 Conservative Identity：
- Shot 内先 Person Detection + Multi-Person Track；
- Track 遇到明确 Face 冲突时立即拆轨，防止遮挡/交叉导致 ID switch；
- 每个 Track 先选高质量、单人干净代表图；
- 跨 Shot 使用 Conservative Identity：Face 有否决权，Body ReID 只做辅助；
- 宁可留下待合并人物碎片，也不把不同人物错误合并到同一个 Character_ID；
- YOLOX / YoutuReID 仍保持 GPU 优先、CPU fallback。

保存层继续经过 character_gallery_persistence_v5：正式 Gallery 与 face-only cover 都不允许带入其他人物。
运行时经过 character_visual_runtime_guard_v5：缺 ONNX Runtime 时整次任务失败并保留旧 Current；
只有 CUDA Provider 不可用时才允许 CPU fallback。

保留本文件只为了让 content_analysis_v2 / 历史测试 import 路径稳定。
"""

from engine.app.character_visual_v5 import (  # noqa: F401
    CandidateDraft,
    CharacterProgress,
    IdentityStatus,
    Observation,
    TrackDraft,
    TrackRepresentative,
    bbox_iou,
    candidate_confidence,
    cosine,
    mean_vector,
    sample_ratios,
    sample_times_us,
)
from engine.app.character_identity_policy_v51 import cluster_candidates  # noqa: F401
from engine.app.character_track_policy_v51 import build_tracks  # noqa: F401
from engine.app.character_track_policy_v5 import select_track_representatives  # noqa: F401
from engine.app.character_visual_runtime_guard_v5 import (  # noqa: F401
    analyze_characters,
    detect_observations,
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
