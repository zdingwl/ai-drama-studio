"""Character V6.1 Shot 内成熟 Multi-Object Tracking。

职责：
- 接收 YOLOX / Face / ReID 的逐帧 Person Observation；
- 默认使用 trackers 2.6 的 BoT-SORT，失败时整条 Shot 从头重跑 ByteTrack；
- 正常 Person 与 V6.1 partial-person proposals 一起进入 MOT，让低分局部人体可以被已有轨迹续上；
- MOT 未确认的低分 partial-person 不直接落成单帧人物，而是先做窄范围时序恢复；
- 只有连续多帧得到空间/ReID 支持的 partial-only Track 才保留为 UNRESOLVED Evidence；
- tracker 只回答 Shot 内连续轨迹，绝不直接创建 Character_ID；
- MOT 后仍执行 Face hard-conflict 拆轨，防止 ID switch 污染身份。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from engine.app import character_visual_v5 as v5
from engine.app.character_track_policy_v51 import _split_track_on_face_conflict

Observation = v5.Observation
TrackDraft = v5.TrackDraft

TRACK_FRAME_RATE = 12.0
# V6.1：0.10~0.32 只允许作为 partial-person 低分候选进入 tracker；Final Identity 门槛不变。
TRACK_ACTIVATION_THRESHOLD = 0.10
TRACK_HIGH_CONF_THRESHOLD = 0.32
TRACK_LOST_BUFFER = 18
TRACK_MIN_CONSECUTIVE = 1
TRACK_MATCH_IOU_FLOOR = 0.10

PARTIAL_RECOVERY_MAX_GAP_US = 400_000
PARTIAL_RECOVERY_REID = 0.72
PARTIAL_RECOVERY_REID_WITH_IOU = 0.56
PARTIAL_RECOVERY_IOU = 0.10
PARTIAL_RECOVERY_STRONG_IOU = 0.34
PARTIAL_TRACK_MIN_SAMPLES = 3
PARTIAL_TRACK_MIN_SPAN_US = 100_000
PARTIAL_TRACK_PAIR_SUPPORT_RATIO = 0.60
PARTIAL_TWO_SAMPLE_REID = 0.90
PARTIAL_TWO_SAMPLE_IOU = 0.48


def _to_xyxy(box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return float(x), float(y), float(x + w), float(y + h)


def _to_xywh(box: Any) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [float(value) for value in box]
    left = int(round(x1))
    top = int(round(y1))
    return left, top, max(1, int(round(x2 - x1))), max(1, int(round(y2 - y1)))


def _is_partial(observation: Observation) -> bool:
    return (
        not bool(observation.face_visible)
        and "partial" in str(observation.detection_source or "").lower()
    )


def _make_bytetrack() -> tuple[Any, str]:
    from trackers import ByteTrackTracker

    tracker = ByteTrackTracker(
        frame_rate=TRACK_FRAME_RATE,
        lost_track_buffer=TRACK_LOST_BUFFER,
        track_activation_threshold=TRACK_ACTIVATION_THRESHOLD,
        minimum_consecutive_frames=TRACK_MIN_CONSECUTIVE,
        high_conf_det_threshold=TRACK_HIGH_CONF_THRESHOLD,
        minimum_iou_threshold=0.18,
    )
    return tracker, "ByteTrack fallback"


def _make_tracker() -> tuple[Any, str]:
    """优先 BoT-SORT；初始化失败时仅降级为同库 ByteTrack，不回到自制 greedy。"""

    try:
        from trackers import BoTSORTTracker

        tracker = BoTSORTTracker(
            frame_rate=TRACK_FRAME_RATE,
            lost_track_buffer=TRACK_LOST_BUFFER,
            track_activation_threshold=TRACK_ACTIVATION_THRESHOLD,
            minimum_consecutive_frames=TRACK_MIN_CONSECUTIVE,
            high_conf_det_threshold=TRACK_HIGH_CONF_THRESHOLD,
            enable_cmc=True,
            cmc_method="sparseOptFlow",
        )
        return tracker, "BoT-SORT"
    except Exception:
        return _make_bytetrack()


def tracker_runtime_status() -> dict[str, object]:
    try:
        tracker, name = _make_tracker()
        del tracker
        return {
            "ready": True,
            "tracker": name,
            "package": "trackers 2.6.0",
            "frame_rate": TRACK_FRAME_RATE,
            "timestamps": True,
            "partial_person_low_threshold": TRACK_ACTIVATION_THRESHOLD,
            "normal_person_threshold": TRACK_HIGH_CONF_THRESHOLD,
            "runtime_fallback": "ByteTrack",
        }
    except Exception as exc:
        return {"ready": False, "tracker": None, "package": "trackers 2.6.0", "error": str(exc)}


def _frame_detections(observations: list[Observation]) -> Any:
    import supervision as sv

    if not observations:
        return sv.Detections(
            xyxy=np.empty((0, 4), dtype=np.float32),
            confidence=np.empty((0,), dtype=np.float32),
            class_id=np.empty((0,), dtype=np.int32),
        )
    xyxy = np.asarray([_to_xyxy(item.bbox) for item in observations], dtype=np.float32)
    confidence = np.asarray(
        [max(0.0, min(1.0, float(item.detection_score))) for item in observations],
        dtype=np.float32,
    )
    class_id = np.zeros((len(observations),), dtype=np.int32)
    return sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)


def _assign_tracker_rows(observations: list[Observation], tracked: Any) -> dict[int, Observation]:
    """把 tracker 输出 bbox 映射回已有 Observation；不能依赖输出顺序。"""

    result: dict[int, Observation] = {}
    tracker_ids = getattr(tracked, "tracker_id", None)
    boxes = getattr(tracked, "xyxy", None)
    if tracker_ids is None or boxes is None:
        return result

    used_observations: set[int] = set()
    for row_index, raw_tracker_id in enumerate(tracker_ids):
        if raw_tracker_id is None:
            continue
        tracker_id = int(raw_tracker_id)
        if tracker_id < 0:
            continue
        tracked_box = _to_xywh(boxes[row_index])
        best_index: int | None = None
        best_iou = -1.0
        for observation_index, observation in enumerate(observations):
            if observation_index in used_observations:
                continue
            score = v5.bbox_iou(tracked_box, observation.bbox)
            if score > best_iou:
                best_iou = score
                best_index = observation_index
        if best_index is None or best_iou < TRACK_MATCH_IOU_FLOOR:
            continue
        used_observations.add(best_index)
        result[tracker_id] = observations[best_index]
    return result


def _partial_pair_supported(left: Observation, right: Observation) -> bool:
    gap = int(right.source_time_us) - int(left.source_time_us)
    if gap <= 0 or gap > PARTIAL_RECOVERY_MAX_GAP_US:
        return False
    iou = v5.bbox_iou(left.bbox, right.bbox)
    reid = v5.cosine(left.reid_embedding, right.reid_embedding)
    if reid is not None and reid >= PARTIAL_RECOVERY_REID:
        return True
    if reid is not None and reid >= PARTIAL_RECOVERY_REID_WITH_IOU and iou >= PARTIAL_RECOVERY_IOU:
        return True
    return iou >= PARTIAL_RECOVERY_STRONG_IOU


def _coalesce_partial_fallbacks(
    tracks_by_id: dict[int, list[Observation]],
) -> dict[int, list[Observation]]:
    """把 tracker 未确认的 partial 单帧碎片按时间连续性恢复成候选 Track。

    正常/Face observation 不参与这一步；这里只处理负 ID fallback，避免改变 Mature MOT 已确认结果。
    """

    result: dict[int, list[Observation]] = defaultdict(list)
    partials: list[Observation] = []
    for track_id, observations in tracks_by_id.items():
        if track_id < 0 and observations and all(_is_partial(item) for item in observations):
            partials.extend(observations)
        else:
            result[track_id].extend(observations)

    groups: list[list[Observation]] = []
    for observation in sorted(partials, key=lambda item: item.source_time_us):
        best_index: int | None = None
        best_score = -1.0
        for index, group in enumerate(groups):
            last = group[-1]
            if not _partial_pair_supported(last, observation):
                continue
            iou = v5.bbox_iou(last.bbox, observation.bbox)
            reid = v5.cosine(last.reid_embedding, observation.reid_embedding)
            score = max(iou, max(0.0, float(reid)) if reid is not None else 0.0)
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None:
            groups.append([observation])
        else:
            groups[best_index].append(observation)

    next_id = min([-1, *(key for key in result if key < 0)]) - 1
    for group in groups:
        result[next_id] = group
        next_id -= 1
    return result


def _partial_track_is_supported(observations: list[Observation]) -> bool:
    """孤立低分 partial proposal 不能成为人物 Evidence；连续时序支持才保留。"""

    ordered = sorted(observations, key=lambda item: item.source_time_us)
    if not ordered or not all(_is_partial(item) for item in ordered):
        return True

    if len(ordered) == 1:
        return False

    span = ordered[-1].source_time_us - ordered[0].source_time_us
    pair_support = sum(
        1
        for left, right in zip(ordered, ordered[1:])
        if _partial_pair_supported(left, right)
    )
    pair_total = max(1, len(ordered) - 1)

    if len(ordered) >= PARTIAL_TRACK_MIN_SAMPLES:
        return (
            span >= PARTIAL_TRACK_MIN_SPAN_US
            and pair_support / pair_total >= PARTIAL_TRACK_PAIR_SUPPORT_RATIO
        )

    # 极短 Shot 可能只有两个命中点；只有非常强的同体证据才保留。
    left, right = ordered
    reid = v5.cosine(left.reid_embedding, right.reid_embedding)
    iou = v5.bbox_iou(left.bbox, right.bbox)
    return (
        span > 0
        and (
            (reid is not None and reid >= PARTIAL_TWO_SAMPLE_REID)
            or iou >= PARTIAL_TWO_SAMPLE_IOU
        )
    )


def _build_track(observations: list[Observation]) -> TrackDraft:
    first = observations[0]
    track = TrackDraft(
        shot_id=first.shot_id,
        episode_id=first.episode_id,
        episode_order=first.episode_order,
        shot_ordinal=first.shot_ordinal,
        observations=sorted(observations, key=lambda item: item.source_time_us),
    )
    v5._refresh_track(track)
    track.representatives = v5.select_track_representatives(track)
    return track


def _track_shot(
    shot_observations: list[Observation],
    tracker: Any,
    tracker_name: str,
) -> dict[int, list[Observation]]:
    """用一个 tracker 完整跑完单 Shot；失败时由调用方整条重跑 fallback。"""

    by_time: dict[int, list[Observation]] = defaultdict(list)
    for observation in shot_observations:
        by_time[observation.source_time_us].append(observation)

    first_observation = shot_observations[0]
    local_times = sorted({item.local_time_us for item in shot_observations})
    frame_map = {
        int(local_us): frame
        for local_us, frame in v5._read_frames(first_observation.reference_path, local_times)
    }

    tracks_by_id: dict[int, list[Observation]] = defaultdict(list)
    fallback_counter = -1
    for source_time_us in sorted(by_time):
        frame_observations = by_time[source_time_us]
        detections = _frame_detections(frame_observations)
        local_us = frame_observations[0].local_time_us if frame_observations else 0
        timestamp = max(0.0, float(local_us) / 1_000_000.0)

        if tracker_name == "BoT-SORT":
            frame = frame_map.get(local_us)
            if frame is None:
                raise RuntimeError("BoT-SORT CMC 缺少当前采样帧")
            tracked = tracker.update(detections, frame=frame, timestamp=timestamp)
        else:
            tracked = tracker.update(detections, timestamp=timestamp)

        assigned = _assign_tracker_rows(frame_observations, tracked)
        assigned_objects = {id(item) for item in assigned.values()}
        for tracker_id, observation in assigned.items():
            tracks_by_id[tracker_id].append(observation)

        # 强 Person / Face 未被 tracker 接住时仍保留 Evidence。
        # 低分 partial 先作为 fallback，Shot 结束后还要经过时序恢复与连续性 Gate。
        for observation in frame_observations:
            if id(observation) in assigned_objects:
                continue
            tracks_by_id[fallback_counter].append(observation)
            fallback_counter -= 1

    return _coalesce_partial_fallbacks(tracks_by_id)


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    """Person Observations -> Mature MOT Tracks。

    每个 Shot 重置 tracker；跨 Shot 身份由 Global Resolver 处理。
    partial-only Track 只有通过连续多帧空间/ReID 确认才保留；孤立低分框直接丢弃。
    """

    by_shot: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        by_shot[observation.shot_id].append(observation)

    result: list[TrackDraft] = []
    for shot_observations in by_shot.values():
        if not shot_observations:
            continue

        tracker, tracker_name = _make_tracker()
        try:
            tracks_by_id = _track_shot(shot_observations, tracker, tracker_name)
        except Exception:
            if tracker_name != "BoT-SORT":
                raise
            fallback_tracker, fallback_name = _make_bytetrack()
            tracks_by_id = _track_shot(shot_observations, fallback_tracker, fallback_name)

        for track_observations in tracks_by_id.values():
            if not track_observations or not _partial_track_is_supported(track_observations):
                continue
            base = _build_track(track_observations)
            # 成熟 MOT 仍可能在复杂交叉处发生 ID switch；Face hard conflict 是最后一道 cannot-link。
            result.extend(_split_track_on_face_conflict(base))

    return sorted(
        result,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
