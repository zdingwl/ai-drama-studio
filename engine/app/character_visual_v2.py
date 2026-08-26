"""人物视觉兼容入口。

正式实现已经升级到 Character V6.3：
- Shot 内约 12fps Person / Partial-Person Observation；
- Face→Person 使用几何安全的一对一归属，partial 不抢 Face；
- trackers 2.6 成熟 MOT（BoT-SORT 优先，ByteTrack fallback）；
- Track 只表达 Shot 内连续人物，不再直接产生身份；
- 整项目 Track 全部完成后运行 Spatiotemporal Global Identity Graph；
- 同 Shot 只有真正同时且空间不同的人才 cannot-link；同人重复 Track 可以去重；
- Face 是身份主证据，CLEAN Body ReID / 时序只做支持；
- RESOLVED Candidate 才允许物化 Final Character；UNRESOLVED 永远只保留 Evidence；
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
    save_candidate_cover,
    save_candidate_gallery,
    select_track_representatives,
)
from engine.app.character_observation_v63 import detect_observations, sample_times_us  # noqa: F401
from engine.app.character_tracking_v6 import build_tracks, tracker_runtime_status  # noqa: F401
from engine.app.character_identity_v63 import resolve_global_identities as cluster_candidates  # noqa: F401
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
