"""人物视觉兼容入口。

正式实现当前处于 Character V9 Phase B：
- Shot 内约 12fps Person / Partial-Person Observation；
- 一帧多人先拆成独立 Person Instance，禁止整帧做人身份图；
- 每个 Instance 标记 CLEAN / OCCLUDED / CONTAMINATED / PARTIAL；
- 同一采样时刻空间不同的 Person Instance 写入 cannot-link Evidence；
- 每个单人人物图分别保留 Person ReID、上下身服装/纹理、Body histogram、身体结构、可选 Face；
- 不生成一个不可解释的“人物总 embedding”；Face 只是可选强证据；
- Track / Candidate Gallery 只允许 CLEAN Person Instance crop 作为正式代表图；
- Gallery 图片同时保存独立特征 sidecar；
- OCCLUDED / CONTAMINATED / PARTIAL 只保留 Evidence，不进入正式 Gallery；
- 身份判断暂时继续复用 V8 Anchor-first，但通过 V9 adapter 重建 CLEAN Gallery；
- V9 Phase C 再替换成完整 Person Gallery Confirm-then-Absorb identity；
- YOLOX / YoutuReID 继续 GPU 优先、CPU fallback。

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
)
from engine.app.character_gallery_v9 import (  # noqa: F401
    save_candidate_cover,
    save_candidate_gallery,
    select_track_representatives,
)
from engine.app.character_observation_v9 import detect_observations, sample_times_us  # noqa: F401
from engine.app.character_tracking_v9 import build_tracks, tracker_runtime_status  # noqa: F401
from engine.app.character_identity_v9a import resolve_global_identities as cluster_candidates  # noqa: F401
from engine.app.character_runtime_v6 import analyze_characters, runtime_status  # noqa: F401


def sample_ratios(duration_us: int) -> tuple[float, ...]:
    duration = max(1, int(duration_us))
    return tuple(value / duration for value in sample_times_us(duration))


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
    "runtime_status",
    "sample_ratios",
    "sample_times_us",
    "save_candidate_cover",
    "save_candidate_gallery",
    "select_track_representatives",
    "tracker_runtime_status",
]
