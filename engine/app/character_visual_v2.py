"""人物视觉兼容入口。

正式实现当前为 Character V10.1：
- 一帧多人先拆成独立 Person Instance，禁止整帧做人身份图；
- 正面 / 侧身 / 背影 / 多人同框拆出的单人 crop 都先作为 Person Evidence；
- CLEAN 不再是唯一 Gallery 入口；证据保存资格与“能否创建新人物”分开；
- 每个单人人物图分别保留 Person ReID、服装、Body、可选 Face；
- YoutuReID Person 模型作为跨视角人物分类主信号；
- 已采集 Person Evidence 再分类到 A / B / C；
- 强 CONTAMINATED / 大面积 PARTIAL 可以提出新人，但必须严格跨 Shot 确认；
- 弱 Partial 只能保存 / 分类 / 挂回已有角色，不能独立创建新人；
- 同帧不同 Person Instance cannot-link 仍是硬约束；
- Track 只负责时序组织，不能决定人物数量。

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
from engine.app.character_gallery_v10 import (  # noqa: F401
    save_candidate_cover,
    save_candidate_gallery,
    select_track_representatives,
)
from engine.app.character_observation_v10 import detect_observations, sample_times_us  # noqa: F401
from engine.app.character_tracking_v10 import build_tracks, tracker_runtime_status  # noqa: F401
from engine.app.character_identity_v101 import resolve_global_identities as cluster_candidates  # noqa: F401
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
