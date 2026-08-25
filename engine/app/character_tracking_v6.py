"""Character V6 Shot 内成熟 Multi-Object Tracking。

职责：
- 接收已经完成 YOLOX / Face / ReID 的逐帧 Person Observation；
- 默认使用 trackers 2.6 的 BoT-SORT 做 Shot 内人物轨迹，启用 Camera Motion Compensation；
- BoT-SORT 初始化失败时仅降级为同库 ByteTrack，不再退回 V5 的自制 greedy tracker；
- tracker 只回答“当前 Shot 内这是不是同一条连续轨迹”，绝不直接创建 Character_ID；
- MOT 结束后仍执行 Face hard-conflict 拆轨，防止遮挡/交叉造成 ID switch 污染整条 Track。

输入：V5 Observation（Person bbox + Face/ReID Evidence）。
输出：TrackDraft。
为什么：V5/V5.1 最大结构问题之一是 6fps + 自制 greedy association。V6 把 Tracking 交给成熟 MOT，
身份判断留给后续 Global Identity Resolver。
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
TRACK_ACTIVATION_THRESHOLD = 0.32
TRACK_HIGH_CONF_THRESHOLD = 0.50
TRACK_LOST_BUFFER = 18
TRACK_MIN_CONSECUTIVE = 1
TRACK_MATCH_IOU_FLOOR = 0.10


def _to_xyxy(box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return float(x), float(y), float(x + w), float(y + h)


def _to_xywh(box: Any) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [float(value) for value in box]
    left = int(round(x1))
    top = int(round(y1))
    return left, top, max(1, int(round(x2 - x1))), max(1, int(round(y2 - y1)))


def _make_tracker() -> tuple[Any, str]:
    """优先 BoT-SORT；仅同库 ByteTrack fallback，不回到自制 greedy。"""

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


def tracker_runtime_status() -> dict[str, object]:
    try:
        tracker, name = _make_tracker()
        del tracker
        return {"ready": True, "tracker": name, "package": "trackers 2.6.0", "frame_rate": TRACK_FRAME_RATE}
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
    confidence = np.asarray([max(0.0, min(1.0, float(item.detection_score))) for item in observations], dtype=np.float32)
    class_id = np.zeros((len(observations),), dtype=np.int32)
    return sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)


def _assign_tracker_rows(observations: list[Observation], tracked: Any) -> dict[int, Observation]:
    """把 tracker 输出 bbox 映射回已有 Observation。

    tracker 可能过滤低置信 detection，因此不能假设返回顺序/数量与输入完全相同。
    """

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


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    """Person Observations -> Mature MOT Tracks。

    每个 Shot 重置 tracker；Shot 之间绝不沿用 MOT ID。跨 Shot 是身份问题，由 Global Resolver 处理。
    """

    by_shot: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        by_shot[observation.shot_id].append(observation)

    result: list[TrackDraft] = []
    for shot_observations in by_shot.values():
        tracker, _tracker_name = _make_tracker()
        by_time: dict[int, list[Observation]] = defaultdict(list)
        for observation in shot_observations:
            by_time[observation.source_time_us].append(observation)

        sample_times = sorted(by_time)
        first_observation = shot_observations[0]
        local_times = sorted({item.local_time_us for item in shot_observations})
        frame_map = {
            int(local_us): frame
            for local_us, frame in v5._read_frames(first_observation.reference_path, local_times)
        }

        tracks_by_id: dict[int, list[Observation]] = defaultdict(list)
        fallback_counter = -1
        for source_time_us in sample_times:
            frame_observations = by_time[source_time_us]
            detections = _frame_detections(frame_observations)
            local_us = frame_observations[0].local_time_us if frame_observations else 0
            frame = frame_map.get(local_us)
            try:
                tracked = tracker.update(detections, frame=frame)
            except TypeError:
                # ByteTrack 等实现接受统一 update API，但不需要 frame。
                tracked = tracker.update(detections)

            assigned = _assign_tracker_rows(frame_observations, tracked)
            assigned_objects = {id(item) for item in assigned.values()}
            for tracker_id, observation in assigned.items():
                tracks_by_id[tracker_id].append(observation)

            # MOT 未确认/过滤掉的 observation 仍保留 Evidence，但只形成临时单独 Track。
            # 后续 Global Resolver 可以把有可靠 Face 的碎片重新并回身份；不会静默漏人。
            for observation in frame_observations:
                if id(observation) in assigned_objects:
                    continue
                tracks_by_id[fallback_counter].append(observation)
                fallback_counter -= 1

        for track_observations in tracks_by_id.values():
            if not track_observations:
                continue
            base = _build_track(track_observations)
            # BoT-SORT 也可能在复杂交叉处发生 ID switch；Face hard conflict 作为最后一道 cannot-link。
            result.extend(_split_track_on_face_conflict(base))

    return sorted(
        result,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
