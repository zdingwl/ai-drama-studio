"""Character V5 Track Representative 最终策略。

职责：
- 如果一个 Track 至少存在一张 CLEAN representative，身份匹配只使用 CLEAN 集合；
- 只有整个 Track 都没有干净帧时，才允许低质量/多人干扰代表图作为临时 Evidence；
- 正式 Character Gallery 仍然只吸收 CLEAN，不会保存脏图。

为什么：多人同框图不应在已经存在更干净身份照片时继续影响 ReID / Gallery Match。
"""
from __future__ import annotations

from engine.app import character_visual_v5 as v5

Observation = v5.Observation
TrackDraft = v5.TrackDraft
TrackRepresentative = v5.TrackRepresentative


def select_track_representatives(track: TrackDraft) -> list[TrackRepresentative]:
    raw = v5.select_track_representatives(track)
    clean = [item for item in raw if item.clean]
    if clean:
        return clean[: v5.TRACK_GALLERY_LIMIT]
    return raw[: v5.TRACK_GALLERY_LIMIT]


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    tracks = v5.build_tracks(observations)
    for track in tracks:
        clean = [item for item in track.representatives if item.clean]
        if clean:
            track.representatives = clean[: v5.TRACK_GALLERY_LIMIT]
        else:
            track.representatives = track.representatives[: v5.TRACK_GALLERY_LIMIT]
    return tracks
