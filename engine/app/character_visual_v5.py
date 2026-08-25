"""03 资产人物视觉 Evidence V5：Track First + Clean Character Gallery。

职责：
- 一个 Shot 内先做 Person Detection，再把每个人从出现到离开连接成独立 Person Track；
- 不再拿单帧 Observation 直接认人，而是先给每个 Track 选多张高质量代表图；
- 代表图优先人物大、清晰、无遮挡、Face/Body 特征明显，并严格排除其他人物污染；
- 跨 Shot 使用 Track Gallery vs Character Gallery 多图比较决定 Character_ID；
- 同一 Character 持续吸收后续 Track 的干净代表图，让身份图库越分析越完整；
- 没有足够身份证据的 Track 保留 UNRESOLVED Evidence，不静默漏人，也不升级 Final Character。

GPU 策略：
- YOLOX Person + YoutuReID 复用 V4.1 ONNX Runtime，默认 CUDA 优先、CPU fallback；
- YuNet / SFace 继续 OpenCV CPU；
- Track association / Gallery matching 在 CPU 完成。

重要保存规则：
- 多人同框可以产生多个 Track；
- 正式 Character Gallery 只接收 CLEAN representative；
- 如果一个 Track 全程都被其他人污染，它仍参与 Evidence / Identity，但不把污染图写入 Character Gallery。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Callable, Literal

from engine.app import character_visual_v4 as legacy
from engine.app.character_visual_gpu_v41 import (
    _YoloXOrtPersonDetector,
    _YoutuReIDOrt,
    _runtime_label,
)
from engine.app.content_models_v2 import require_models
from engine.app.studio_v2 import new_id, workspace_root

CharacterProgress = Callable[[int, int, str], None]
IdentityStatus = Literal["RESOLVED", "UNRESOLVED"]

# Track sampling：Reference Clip 中约每 166ms 一次人物检测；极长 Shot 控制上限，避免无限放大成本。
TRACK_SAMPLE_FPS = 6.0
TRACK_MIN_SAMPLES = 3
TRACK_MAX_SAMPLES = 30
TRACK_MAX_GAP_US = 650_000

# Track 内关联。
TRACK_FACE_MATCH = 0.34
TRACK_REID_MATCH = 0.62
TRACK_REID_WITH_IOU = 0.52
TRACK_MIN_IOU = 0.12

# Gallery：每 Track 最多 6 张；每 Character 内存 Gallery 最多保留 24 张高质量、多样化图。
TRACK_GALLERY_LIMIT = 6
CHARACTER_GALLERY_LIMIT = 24
CLEAN_INTERFERENCE_MAX = 0.025
SAVE_CONTAMINATION_MAX = 0.015
REPRESENTATIVE_DIVERSITY_REID = 0.965
REPRESENTATIVE_DIVERSITY_FACE = 0.955

# Character Gallery matching。
FACE_STRONG_MATCH = 0.50
FACE_SUPPORTED_MATCH = 0.36
REID_SUPPORT_MATCH = 0.56
REID_STRONG_MATCH = 0.76
BODY_ONLY_MAX_SHOT_GAP = 4
SECOND_PASS_FACE_MATCH = 0.52


@dataclass
class Observation(legacy.Observation):
    """一个采样时刻里明确检测到的一名 Person，并保存代表图质量 Evidence。"""

    frame_width: int = 0
    frame_height: int = 0
    face_score: float = 0.0
    clarity_score: float = 0.0
    body_completeness: float = 0.0
    interference_ratio: float = 0.0
    other_person_boxes: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass
class TrackRepresentative:
    """Track 的一张身份代表图；clean=True 才允许进入正式 Character Gallery。"""

    observation: Observation
    quality_score: float
    clean: bool


@dataclass
class TrackDraft(legacy.TrackDraft):
    """一个人物在一个 Shot 内从出现到离开的轨迹。"""

    representatives: list[TrackRepresentative] = field(default_factory=list)

    @property
    def start_us(self) -> int | None:
        return min((item.source_time_us for item in self.observations), default=None)

    @property
    def end_us(self) -> int | None:
        return max((item.source_time_us for item in self.observations), default=None)


@dataclass
class CandidateDraft(legacy.CandidateDraft):
    """跨 Shot Character_ID Candidate；gallery 会随着后续 Track 持续丰富。"""

    gallery: list[TrackRepresentative] = field(default_factory=list)


# 兼容旧调用。
cosine = legacy.cosine
mean_vector = legacy.mean_vector
bbox_iou = legacy.bbox_iou


def sample_times_us(duration_us: int) -> tuple[int, ...]:
    """按时长生成 Track 采样时间。

    输入：Shot 时长（Source us）。
    输出：Reference Clip 内相对时间点。
    为什么：V4 的 3/5/7/9 帧适合“找证据”，不够表达人物进入、遮挡、离开的轨迹；
    V5 用约 6fps 的连续采样建立 Track，同时用上限控制本地推理成本。
    """

    duration = max(1, int(duration_us))
    seconds = duration / 1_000_000.0
    count = max(TRACK_MIN_SAMPLES, int(math.ceil(seconds * TRACK_SAMPLE_FPS)) + 1)
    count = min(TRACK_MAX_SAMPLES, count)
    if count <= 1:
        return (duration // 2,)
    start = min(duration - 1, max(0, int(duration * 0.02)))
    end = min(duration - 1, max(start, int(duration * 0.98)))
    if count == 2:
        return (start, end)
    step = (end - start) / max(1, count - 1)
    return tuple(sorted({max(0, min(duration - 1, int(round(start + step * index)))) for index in range(count)}))


def sample_ratios(duration_us: int) -> tuple[float, ...]:
    """历史测试兼容：返回 V5 采样点对应比例。"""

    duration = max(1, int(duration_us))
    return tuple(value / duration for value in sample_times_us(duration))


def _intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    return max(0, right - left) * max(0, bottom - top)


def _interference_ratio(target: tuple[int, int, int, int], others: list[tuple[int, int, int, int]]) -> float:
    area = max(1, target[2] * target[3])
    overlap = sum(_intersection_area(target, other) for other in others)
    return min(1.0, overlap / area)


def _clarity_score(frame: Any, bbox: tuple[int, int, int, int]) -> float:
    import cv2

    x, y, w, h = bbox
    crop = frame[max(0, y):max(0, y) + max(1, h), max(0, x):max(0, x) + max(1, w)]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # 约 300~600 的 Laplacian variance 已经是较清晰人物；使用压缩映射避免极端值支配。
    return max(0.0, min(1.0, math.log1p(variance) / math.log1p(600.0)))


def _body_completeness(bbox: tuple[int, int, int, int], width: int, height: int) -> float:
    x, y, w, h = bbox
    margin_x = max(2, int(width * 0.01))
    margin_y = max(2, int(height * 0.01))
    touches = int(x <= margin_x) + int(y <= margin_y) + int(x + w >= width - margin_x) + int(y + h >= height - margin_y)
    return max(0.20, 1.0 - touches * 0.20)


def _representative_quality(observation: Observation) -> float:
    frame_area = max(1, observation.frame_width * observation.frame_height)
    person_area = max(1, observation.bbox[2] * observation.bbox[3])
    size_score = min(1.0, (person_area / frame_area) / 0.28)
    face_area = 0
    if observation.face_bbox is not None:
        face_area = max(1, observation.face_bbox[2] * observation.face_bbox[3])
    face_size_score = min(1.0, (face_area / frame_area) / 0.035) if face_area else 0.0
    face_score = max(0.0, min(1.0, observation.face_score))
    interference_penalty = min(1.0, observation.interference_ratio * 3.2)
    quality = (
        size_score * 0.24
        + observation.clarity_score * 0.23
        + observation.body_completeness * 0.17
        + face_score * 0.18
        + face_size_score * 0.10
        + max(0.0, min(1.0, observation.detection_score)) * 0.08
        - interference_penalty * 0.42
    )
    return max(0.0, min(1.0, quality))


def _representative_diverse(left: TrackRepresentative, right: TrackRepresentative) -> bool:
    face = cosine(left.observation.face_embedding, right.observation.face_embedding)
    reid = cosine(left.observation.reid_embedding, right.observation.reid_embedding)
    time_gap = abs(left.observation.source_time_us - right.observation.source_time_us)
    if face is not None and face < REPRESENTATIVE_DIVERSITY_FACE:
        return True
    if reid is not None and reid < REPRESENTATIVE_DIVERSITY_REID:
        return True
    return time_gap >= 500_000


def select_track_representatives(track: TrackDraft) -> list[TrackRepresentative]:
    """从完整 Track 中挑高质量、多样化代表图。

    CLEAN 的定义不是“只有一个检测框”，而是目标 Person bbox 与同帧其他 Person bbox 几乎不重叠。
    脏图可以作为 Track 内身份 Evidence，但不会进入正式 Character Gallery。
    """

    scored = [
        TrackRepresentative(
            observation=item,
            quality_score=_representative_quality(item),
            clean=item.interference_ratio <= CLEAN_INTERFERENCE_MAX,
        )
        for item in track.observations
        if isinstance(item, Observation)
    ]
    scored.sort(key=lambda item: (1 if item.clean else 0, item.quality_score), reverse=True)
    selected: list[TrackRepresentative] = []
    for item in scored:
        if selected and not any(_representative_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        if len(selected) >= TRACK_GALLERY_LIMIT:
            break
    if not selected and scored:
        selected.append(scored[0])
    return selected


def _refresh_track(track: TrackDraft) -> None:
    track.face_embedding = mean_vector([item.face_embedding for item in track.observations if item.face_embedding is not None])
    track.reid_embedding = mean_vector([item.reid_embedding for item in track.observations if item.reid_embedding is not None])
    track.body_hist = mean_vector([item.body_hist for item in track.observations if item.body_hist is not None])


def _track_match_score(track: TrackDraft, observation: Observation) -> float | None:
    if not track.observations:
        return None
    last = track.observations[-1]
    if observation.source_time_us - last.source_time_us > TRACK_MAX_GAP_US:
        return None
    face = cosine(track.face_embedding, observation.face_embedding)
    reid = cosine(track.reid_embedding, observation.reid_embedding)
    spatial = bbox_iou(last.bbox, observation.bbox)
    qualifies = (
        (face is not None and face >= TRACK_FACE_MATCH)
        or (reid is not None and reid >= TRACK_REID_MATCH)
        or (reid is not None and reid >= TRACK_REID_WITH_IOU and spatial >= TRACK_MIN_IOU)
    )
    if not qualifies:
        return None
    return max(0.0, face or 0.0) * 0.52 + max(0.0, reid or 0.0) * 0.36 + spatial * 0.12


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    """Shot 内 Multi-Person Tracking。

    输入：按帧 Person Observations。
    输出：每个“进入→持续出现/短遮挡→离开”的 Track。
    为什么：身份判断必须发生在 Track 之后，不能让某一帧的检测结果直接创建 Character。
    """

    by_shot: dict[str, list[Observation]] = {}
    for item in observations:
        by_shot.setdefault(item.shot_id, []).append(item)

    result: list[TrackDraft] = []
    for shot_observations in by_shot.values():
        tracks: list[TrackDraft] = []
        by_time: dict[int, list[Observation]] = {}
        for observation in shot_observations:
            by_time.setdefault(observation.source_time_us, []).append(observation)

        for source_time_us in sorted(by_time):
            frame_observations = by_time[source_time_us]
            pairs: list[tuple[float, int, int]] = []
            for track_index, track in enumerate(tracks):
                for obs_index, observation in enumerate(frame_observations):
                    score = _track_match_score(track, observation)
                    if score is not None:
                        pairs.append((score, track_index, obs_index))
            used_tracks: set[int] = set()
            used_observations: set[int] = set()
            for _score, track_index, obs_index in sorted(pairs, reverse=True):
                if track_index in used_tracks or obs_index in used_observations:
                    continue
                tracks[track_index].observations.append(frame_observations[obs_index])
                _refresh_track(tracks[track_index])
                used_tracks.add(track_index)
                used_observations.add(obs_index)
            for obs_index, observation in enumerate(frame_observations):
                if obs_index in used_observations:
                    continue
                track = TrackDraft(
                    shot_id=observation.shot_id,
                    episode_id=observation.episode_id,
                    episode_order=observation.episode_order,
                    shot_ordinal=observation.shot_ordinal,
                    observations=[observation],
                )
                _refresh_track(track)
                tracks.append(track)

        for track in tracks:
            track.representatives = select_track_representatives(track)
        result.extend(tracks)
    return result


def _read_frames(reference_path: str, local_times_us: list[int]) -> list[tuple[int, Any]]:
    return legacy._read_frames(reference_path, local_times_us)


def _read_frame(reference_path: str, local_time_us: int) -> Any | None:
    return legacy._read_frame(reference_path, local_time_us)


def detect_observations(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[Observation]:
    """V5 Person Detection + Face + ReID Evidence。

    每个 Shot 先在较连续的时间点数清 Person，再交给 build_tracks 建轨迹。
    """

    import cv2

    models = require_models()
    person_detector = _YoloXOrtPersonDetector(models["person_detection.yolox.2022nov"])
    reid = _YoutuReIDOrt(models["person_reid.youtu.2021nov"])
    runtime_label = _runtime_label(person_detector, reid)

    face_detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]),
        "",
        (320, 320),
        score_threshold=legacy.FACE_DETECTION_THRESHOLD,
        nms_threshold=0.30,
        top_k=5000,
    )
    face_recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")

    observations: list[Observation] = []
    total = len(shots)
    for shot_index, shot in enumerate(shots, start=1):
        if progress:
            progress(shot_index, total, f"人物 V5 · Track First · {runtime_label}：Shot {shot_index} / {total}")
        duration_us = max(1, int(shot["duration_us"]))
        local_times = list(sample_times_us(duration_us))
        for local_us, frame in _read_frames(shot["reference_path"], local_times):
            height, width = frame.shape[:2]
            persons = person_detector.detect(frame)
            person_boxes = [item[0] for item in persons]

            face_detector.setInputSize((width, height))
            _, face_rows = face_detector.detect(frame)
            faces: list[tuple[Any, tuple[int, int, int, int], float]] = []
            if face_rows is not None:
                for row in face_rows:
                    x, y, w, h = [int(round(float(value))) for value in row[:4]]
                    box = legacy._clamp_box((x, y, w, h), width, height)
                    if box is None or box[2] < 18 or box[3] < 18:
                        continue
                    faces.append((row, box, float(row[-1])))

            used_faces: set[int] = set()
            for person_index, (person_box, person_score) in enumerate(sorted(persons, key=lambda item: item[1], reverse=True)):
                # sorted 后不能拿 person_index 去排除原 person_boxes，因此按 bbox 值过滤当前框。
                other_boxes = [box for box in person_boxes if box != person_box]
                matching: list[tuple[int, Any, tuple[int, int, int, int], float]] = []
                for face_index, (row, face_box, face_score) in enumerate(faces):
                    if face_index in used_faces:
                        continue
                    if legacy._point_inside(legacy._center(face_box), person_box):
                        matching.append((face_index, row, face_box, face_score))
                face_row = None
                face_box = None
                face_score = 0.0
                if matching:
                    face_index, face_row, face_box, face_score = max(matching, key=lambda item: item[3])
                    used_faces.add(face_index)
                observations.append(Observation(
                    shot_id=shot["id"],
                    episode_id=shot["episode_id"],
                    episode_order=shot["episode_order"],
                    shot_ordinal=shot["ordinal"],
                    source_time_us=shot["start_us"] + local_us,
                    local_time_us=local_us,
                    bbox=person_box,
                    face_bbox=face_box,
                    reference_path=shot["reference_path"],
                    detection_score=max(person_score, face_score),
                    face_embedding=legacy._face_embedding(face_recognizer, frame, face_row) if face_row is not None else None,
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=legacy._body_histogram(frame, person_box),
                    face_visible=face_row is not None,
                    detection_source="v5-yolox-ort+face" if face_row is not None else "v5-yolox-ort",
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=_clarity_score(frame, person_box),
                    body_completeness=_body_completeness(person_box, width, height),
                    interference_ratio=_interference_ratio(person_box, other_boxes),
                    other_person_boxes=other_boxes,
                ))

            # 大特写 fallback：YOLOX 没完整 person 时，高置信 Face 仍建立独立 Track Evidence。
            for face_index, (row, face_box, face_score) in enumerate(faces):
                if face_index in used_faces or face_score < legacy.FACE_FALLBACK_THRESHOLD:
                    continue
                person_box = legacy._synthetic_body_box(face_box, width, height)
                other_boxes = list(person_boxes)
                observations.append(Observation(
                    shot_id=shot["id"],
                    episode_id=shot["episode_id"],
                    episode_order=shot["episode_order"],
                    shot_ordinal=shot["ordinal"],
                    source_time_us=shot["start_us"] + local_us,
                    local_time_us=local_us,
                    bbox=person_box,
                    face_bbox=face_box,
                    reference_path=shot["reference_path"],
                    detection_score=face_score,
                    face_embedding=legacy._face_embedding(face_recognizer, frame, row),
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=legacy._body_histogram(frame, person_box),
                    face_visible=True,
                    detection_source="v5-face-fallback",
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=_clarity_score(frame, person_box),
                    body_completeness=_body_completeness(person_box, width, height),
                    interference_ratio=_interference_ratio(person_box, other_boxes),
                    other_person_boxes=other_boxes,
                ))
    return observations


def _track_interval(track: TrackDraft) -> tuple[int | None, int | None]:
    if not track.observations:
        return None, None
    return min(item.source_time_us for item in track.observations), max(item.source_time_us for item in track.observations)


def _simultaneous_conflict(candidate: CandidateDraft, track: TrackDraft) -> bool:
    """同一个 Shot 同时出现的两个 Track 永远不能绑定到同一 Character_ID。"""

    for member in candidate.tracks:
        if member.shot_id != track.shot_id:
            continue
        left_start, left_end = _track_interval(member)
        right_start, right_end = _track_interval(track)
        # 历史/测试 Track 没时间 Evidence 时，为安全起见按同框冲突处理。
        if left_start is None or right_start is None:
            return True
        if max(left_start, right_start) <= min(left_end or left_start, right_end or right_start):
            return True
    return False


def _track_gap(candidate: CandidateDraft, track: TrackDraft) -> int | None:
    gaps = [
        abs(member.shot_ordinal - track.shot_ordinal)
        for member in candidate.tracks
        if member.episode_id == track.episode_id
    ]
    return min(gaps) if gaps else None


def _pairwise_top_average(values: list[float | None], top_n: int = 3) -> float | None:
    clean = sorted((value for value in values if value is not None), reverse=True)
    if not clean:
        return None
    selected = clean[:top_n]
    return sum(selected) / len(selected)


def _gallery_similarity(candidate: CandidateDraft, track: TrackDraft) -> tuple[float | None, float | None]:
    track_reps = track.representatives
    candidate_reps = candidate.gallery
    face_values: list[float | None] = []
    reid_values: list[float | None] = []
    if candidate_reps and track_reps:
        for left in candidate_reps:
            for right in track_reps:
                face_values.append(cosine(left.observation.face_embedding, right.observation.face_embedding))
                reid_values.append(cosine(left.observation.reid_embedding, right.observation.reid_embedding))
    face = _pairwise_top_average(face_values)
    reid = _pairwise_top_average(reid_values)
    # 没有真实 representative（例如历史测试/旧 Evidence）时回退 Track/Candidate 聚合 embedding。
    if face is None:
        face = cosine(candidate.face_embedding, track.face_embedding)
    if reid is None:
        reid = cosine(candidate.reid_embedding, track.reid_embedding)
    return face, reid


def _candidate_match_score(candidate: CandidateDraft, track: TrackDraft) -> float | None:
    if _simultaneous_conflict(candidate, track):
        return None
    face, reid = _gallery_similarity(candidate, track)
    gap = _track_gap(candidate, track)
    strong_face = face is not None and face >= FACE_STRONG_MATCH
    supported_face = face is not None and face >= FACE_SUPPORTED_MATCH and reid is not None and reid >= REID_SUPPORT_MATCH
    body_continuity = reid is not None and reid >= REID_STRONG_MATCH and gap is not None and gap <= BODY_ONLY_MAX_SHOT_GAP
    if not (strong_face or supported_face or body_continuity):
        return None
    temporal_bonus = 0.04 if gap is not None and gap <= 2 else 0.0
    return max(0.0, face or 0.0) * 0.68 + max(0.0, reid or 0.0) * 0.28 + temporal_bonus


def _refresh_candidate(candidate: CandidateDraft) -> None:
    candidate.face_embedding = mean_vector([track.face_embedding for track in candidate.tracks if track.face_embedding is not None])
    candidate.reid_embedding = mean_vector([track.reid_embedding for track in candidate.tracks if track.reid_embedding is not None])
    candidate.body_hist = mean_vector([track.body_hist for track in candidate.tracks if track.body_hist is not None])
    candidate.identity_status = "RESOLVED" if candidate.face_embedding is not None else "UNRESOLVED"

    # 正式 Character Gallery 只吸收 clean 图；按质量 + 多样性压缩，避免一个长 Track 塞满近重复照片。
    pool = [rep for track in candidate.tracks for rep in track.representatives if rep.clean]
    pool.sort(key=lambda item: item.quality_score, reverse=True)
    selected: list[TrackRepresentative] = []
    for item in pool:
        if selected and not any(_representative_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        if len(selected) >= CHARACTER_GALLERY_LIMIT:
            break
    candidate.gallery = selected


def _append_track(candidate: CandidateDraft, track: TrackDraft, score: float | None = None) -> None:
    candidate.tracks.append(track)
    if score is not None:
        candidate.scores.append(score)
    _refresh_candidate(candidate)


def _candidate_pair_score(left: CandidateDraft, right: CandidateDraft) -> float | None:
    # 任何同 Shot 同时存在的 Track 都是强负证据。
    for track in right.tracks:
        if _simultaneous_conflict(left, track):
            return None
    face_values: list[float | None] = []
    reid_values: list[float | None] = []
    if left.gallery and right.gallery:
        for a in left.gallery:
            for b in right.gallery:
                face_values.append(cosine(a.observation.face_embedding, b.observation.face_embedding))
                reid_values.append(cosine(a.observation.reid_embedding, b.observation.reid_embedding))
    face = _pairwise_top_average(face_values) or cosine(left.face_embedding, right.face_embedding)
    reid = _pairwise_top_average(reid_values) or cosine(left.reid_embedding, right.reid_embedding)
    if face is None or face < SECOND_PASS_FACE_MATCH:
        return None
    return face * 0.78 + max(0.0, reid or 0.0) * 0.22


def _merge_candidate_fragments(candidates: list[CandidateDraft]) -> list[CandidateDraft]:
    """第二遍 Gallery 去碎片：Face 强一致且不存在同框冲突时合并 Character。"""

    changed = True
    while changed:
        changed = False
        best: tuple[float, int, int] | None = None
        for left_index in range(len(candidates)):
            for right_index in range(left_index + 1, len(candidates)):
                score = _candidate_pair_score(candidates[left_index], candidates[right_index])
                if score is not None and (best is None or score > best[0]):
                    best = (score, left_index, right_index)
        if best is None:
            break
        score, left_index, right_index = best
        source = candidates[right_index]
        for track in source.tracks:
            _append_track(candidates[left_index], track, score)
        del candidates[right_index]
        changed = True
    return candidates


def cluster_candidates(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    """Track Gallery → Character Gallery。

    处理顺序就是视频顺序，因此一个 Character_ID 的图库会随着后续 Shot 持续增加。
    Body-only Track 可以挂回已有 Character，也可以暂存 UNRESOLVED；后面一旦露脸并匹配，Candidate 会自动升级 RESOLVED。
    """

    ordered = sorted(
        tracks,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if isinstance(item, TrackDraft) and item.start_us is not None else -1,
        ),
    )
    candidates: list[CandidateDraft] = []
    for track in ordered:
        best_candidate: CandidateDraft | None = None
        best_score = -1.0
        for candidate in candidates:
            score = _candidate_match_score(candidate, track)
            if score is not None and score > best_score:
                best_candidate, best_score = candidate, score
        if best_candidate is None:
            best_candidate = CandidateDraft(
                id=new_id("CHAR_CANDIDATE"),
                identity_status="RESOLVED" if track.face_embedding is not None else "UNRESOLVED",
            )
            candidates.append(best_candidate)
            _append_track(best_candidate, track)
        else:
            _append_track(best_candidate, track, best_score)
    return _merge_candidate_fragments(candidates)


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[CandidateDraft]:
    """人物 V5 总入口：Person → Track → Track Gallery → Character Gallery。"""

    observations = detect_observations(shots, progress=progress)
    tracks = build_tracks(observations)
    return cluster_candidates(tracks)


def candidate_confidence(candidate: CandidateDraft) -> float | None:
    if candidate.identity_status == "UNRESOLVED":
        detections = [obs.detection_score for track in candidate.tracks for obs in track.observations]
        return min(0.69, sum(detections) / len(detections)) if detections else 0.50
    if candidate.scores:
        return max(0.0, min(0.99, sum(candidate.scores) / len(candidate.scores)))
    face_scores = [
        obs.face_score if isinstance(obs, Observation) else obs.detection_score
        for track in candidate.tracks for obs in track.observations if obs.face_visible
    ]
    return min(0.95, sum(face_scores) / len(face_scores)) if face_scores else None


def _expanded_crop_bounds(bbox: tuple[int, int, int, int], width: int, height: int, margin: float = 0.05) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    pad_x, pad_y = int(w * margin), int(h * margin)
    left = max(0, x - pad_x)
    top = max(0, y - pad_y)
    right = min(width, x + w + pad_x)
    bottom = min(height, y + h + pad_y)
    return left, top, right, bottom


def _crop_contamination(bounds: tuple[int, int, int, int], others: list[tuple[int, int, int, int]]) -> float:
    left, top, right, bottom = bounds
    crop_box = (left, top, max(1, right - left), max(1, bottom - top))
    area = max(1, crop_box[2] * crop_box[3])
    return min(1.0, sum(_intersection_area(crop_box, other) for other in others) / area)


def _save_clean_representative(path: Path, representative: TrackRepresentative) -> bool:
    """只保存目标人物自己。

    先尝试轻微留边的人物 crop；如果留边会带入别人，收紧到目标 bbox；如果仍有明显多人重叠则拒绝写入图库。
    这里故意不“糊掉别人后假装干净”，因为被遮挡区域无法可靠恢复目标人物本身。
    """

    import cv2

    obs = representative.observation
    if not representative.clean:
        return False
    frame = _read_frame(obs.reference_path, obs.local_time_us)
    if frame is None:
        return False
    height, width = frame.shape[:2]
    bounds = _expanded_crop_bounds(obs.bbox, width, height, margin=0.06)
    if _crop_contamination(bounds, obs.other_person_boxes) > SAVE_CONTAMINATION_MAX:
        x, y, w, h = obs.bbox
        bounds = (max(0, x), max(0, y), min(width, x + w), min(height, y + h))
    if _crop_contamination(bounds, obs.other_person_boxes) > SAVE_CONTAMINATION_MAX:
        return False
    left, top, right, bottom = bounds
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(path), crop))


def save_candidate_gallery(run_id: str, candidate: CandidateDraft, ordinal: int) -> list[str]:
    """把内存 Character Gallery 保存成单人图库，并写 manifest。

    输出路径只包含通过 clean + contamination 双重门槛的图片。
    """

    root = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}"
    saved: list[str] = []
    manifest_images: list[dict[str, Any]] = []
    for index, representative in enumerate(candidate.gallery, start=1):
        path = root / f"gallery_{index:02d}.jpg"
        if not _save_clean_representative(path, representative):
            continue
        saved.append(str(path))
        obs = representative.observation
        manifest_images.append({
            "path": str(path),
            "shot_id": obs.shot_id,
            "source_time_us": obs.source_time_us,
            "quality": round(representative.quality_score, 6),
            "face_visible": obs.face_visible,
            "interference_ratio": round(obs.interference_ratio, 6),
            "isolation": "clean-person-crop",
        })
    root.mkdir(parents=True, exist_ok=True)
    (root / "gallery.json").write_text(json.dumps({
        "candidate_id": candidate.id,
        "identity_status": candidate.identity_status,
        "policy": "track-first-gallery-match; formal gallery contains target person only",
        "image_count": len(manifest_images),
        "images": manifest_images,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def _save_face_only_fallback(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    """没有干净身体图时只给 UI 生成 face-only cover；它不计入 Character Gallery。"""

    import cv2

    face_observations = [
        obs for track in candidate.tracks for obs in track.observations
        if obs.face_visible and obs.face_bbox is not None
    ]
    if not face_observations:
        return None
    obs = max(face_observations, key=lambda item: getattr(item, "face_score", item.detection_score))
    frame = _read_frame(obs.reference_path, obs.local_time_us)
    if frame is None or obs.face_bbox is None:
        return None
    x, y, w, h = obs.face_bbox
    height, width = frame.shape[:2]
    pad = int(max(w, h) * 0.30)
    left, top = max(0, x - pad), max(0, y - pad)
    right, bottom = min(width, x + w + pad), min(height, y + h + pad)
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    path = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}" / "cover_face_only.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path) if cv2.imwrite(str(path), crop) else None


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    """保存 Character Gallery 并返回最优单人图作为封面。"""

    paths = save_candidate_gallery(run_id, candidate, ordinal)
    if paths:
        return paths[0]
    return _save_face_only_fallback(run_id, candidate, ordinal)
