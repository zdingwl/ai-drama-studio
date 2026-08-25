"""Character V5.1 Shot 内 Track 防串人策略。

职责：
- 继续复用 V5 的 Person Detection / 初始 Multi-Person Tracking；
- 如果同一 Track 后续出现与已有 Face anchor 明显冲突的人脸，立即从冲突帧拆成新 Track；
- Track 有 CLEAN representative 时，仍然只保留 CLEAN representative 参与后续身份判断。

为什么：
多人交叉、遮挡或相似服装时，Body ReID 可能把 A 的轨迹续到 B 身上。
如果此时仍允许整条 Track 进入 Character Gallery，跨 Shot 再严格也已经来不及。
V5.1 因此在 Track 层增加 Face cannot-link：明显不同的人脸不能留在同一 Track。
"""
from __future__ import annotations

from engine.app import character_visual_v5 as v5
from engine.app.character_track_policy_v5 import select_track_representatives

Observation = v5.Observation
TrackDraft = v5.TrackDraft
TrackRepresentative = v5.TrackRepresentative

# 这是 hard conflict，不是普通“匹配阈值”。只有明显不像才拆，避免侧脸/表情变化造成过度断轨。
TRACK_FACE_HARD_CONFLICT = 0.28


def _build_segment(source: TrackDraft, observations: list[Observation]) -> TrackDraft:
    segment = TrackDraft(
        shot_id=source.shot_id,
        episode_id=source.episode_id,
        episode_order=source.episode_order,
        shot_ordinal=source.shot_ordinal,
        observations=list(observations),
    )
    v5._refresh_track(segment)
    segment.representatives = select_track_representatives(segment)
    return segment


def _split_track_on_face_conflict(track: TrackDraft) -> list[TrackDraft]:
    ordered = sorted(track.observations, key=lambda item: item.source_time_us)
    if len(ordered) <= 1:
        return [_build_segment(track, list(ordered))]

    result: list[TrackDraft] = []
    current: list[Observation] = []
    current_faces: list[object] = []

    for observation in ordered:
        should_split = False
        if observation.face_embedding is not None and current_faces:
            anchor = v5.mean_vector(current_faces)
            similarity = v5.cosine(anchor, observation.face_embedding)
            should_split = similarity is not None and similarity < TRACK_FACE_HARD_CONFLICT

        if should_split and current:
            result.append(_build_segment(track, current))
            current = []
            current_faces = []

        current.append(observation)
        if observation.face_embedding is not None:
            current_faces.append(observation.face_embedding)

    if current:
        result.append(_build_segment(track, current))
    return result


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    """生成 V5.1 Track。

    输入：逐帧 Person Observation。
    输出：Shot 内人物 Track；Face hard conflict 会被拆开。
    """

    base_tracks = v5.build_tracks(observations)
    result: list[TrackDraft] = []
    for track in base_tracks:
        result.extend(_split_track_on_face_conflict(track))
    return result
