"""人物视觉兼容入口。

正式实现当前处于 Character V9 Phase A：
- Shot 内约 12fps Person / Partial-Person Observation；
- 一帧多人先拆成独立 Person Instance，禁止整帧做人身份图；
- 每个 Instance 标记 CLEAN / OCCLUDED / CONTAMINATED / PARTIAL；
- 同一采样时刻空间不同的 Person Instance 写入 cannot-link Evidence；
- Track Gallery 只允许 CLEAN Person Instance crop 作为正式代表图；
- OCCLUDED / CONTAMINATED / PARTIAL 只保留 Evidence，不进入正式 Gallery；
- 身份解析暂时继续复用 V8 Anchor-first，后续 V9 Phase B/C 再替换成 Person Gallery identity；
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
from engine.app.character_identity_v8 import resolve_global_identities as cluster_candidates  # noqa: F401
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
