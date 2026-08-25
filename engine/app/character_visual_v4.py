"""03 资产人物视觉 Evidence V4。

职责：
- YOLOX 先回答“画面里有几个人”，避免没识别到脸就把人物静默漏掉；
- YuNet + SFace 在露脸时提供强身份锚点；
- YoutuReID 为侧脸、背影、遮挡提供专用人体外观 embedding；
- 自适应多帧采样 + Shot 内 Track 降低只抽 3 帧造成的漏检；
- 跨 Shot 聚类后再做 Candidate 二次合并，降低同一演员被碎片化成多个人物；
- 没有 Face anchor、但 Person Detector 明确检测到的人保留为 UNRESOLVED Evidence，
  只用于“这里有人但身份未确定”的异常提示，绝不直接升级成 Final Character。

输入：当前 Project 的全部 Current Shot / Reference Clip。
输出：CandidateDraft + TrackDraft，仅作为不可变 AI Evidence。
为什么：人物身份是后续 Speaker、Dialogue、重制资产绑定的 Source of Truth，宁可显式标记
“身份未确定”，也不能把画面里的人静默丢掉。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from engine.app.content_models_v2 import require_models
from engine.app.studio_v2 import new_id, workspace_root

CharacterProgress = Callable[[int, int, str], None]
IdentityStatus = Literal["RESOLVED", "UNRESOLVED"]

# Face/SFace：SFace 官方 cosine 同人阈值附近约 0.36；这里结合 ReID / 时间关系使用，
# 不再用一个过高阈值把侧脸、表情变化全部拆开。
FACE_DETECTION_THRESHOLD = 0.72
FACE_FALLBACK_THRESHOLD = 0.86
FACE_STRONG_MATCH = 0.48
FACE_SUPPORTED_MATCH = 0.36

# YOLOX / YoutuReID。
PERSON_SCORE_THRESHOLD = 0.32
PERSON_NMS_THRESHOLD = 0.45
TRACK_FACE_THRESHOLD = 0.34
TRACK_REID_THRESHOLD = 0.64
TRACK_REID_SPATIAL_THRESHOLD = 0.54
RESOLVED_REID_THRESHOLD = 0.70
UNRESOLVED_REID_THRESHOLD = 0.78
CANDIDATE_REID_SUPPORT = 0.55
MAX_BODY_ATTACH_GAP = 4
MAX_UNRESOLVED_CLUSTER_GAP = 3


@dataclass
class Observation:
    """一个采样时刻里明确检测到的一名 Person。"""

    shot_id: str
    episode_id: str
    episode_order: int
    shot_ordinal: int
    source_time_us: int
    local_time_us: int
    bbox: tuple[int, int, int, int]
    face_bbox: tuple[int, int, int, int] | None
    reference_path: str
    detection_score: float
    face_embedding: Any | None
    reid_embedding: Any | None
    body_hist: Any | None
    face_visible: bool
    detection_source: str


@dataclass
class TrackDraft:
    """同一个 Shot 内跨采样帧的一名人物 Track。"""

    shot_id: str
    episode_id: str
    episode_order: int
    shot_ordinal: int
    observations: list[Observation] = field(default_factory=list)
    face_embedding: Any | None = None
    reid_embedding: Any | None = None
    body_hist: Any | None = None


@dataclass
class CandidateDraft:
    """跨 Shot 人物身份候选。

    RESOLVED：至少有一个 Face/SFace anchor，可升级成 Final Character。
    UNRESOLVED：Person Detector 明确检测到人，但身份证据还不足，只保留 Evidence。
    """

    id: str
    tracks: list[TrackDraft] = field(default_factory=list)
    face_embedding: Any | None = None
    reid_embedding: Any | None = None
    body_hist: Any | None = None
    scores: list[float] = field(default_factory=list)
    identity_status: IdentityStatus = "UNRESOLVED"

    @property
    def has_face_anchor(self) -> bool:
        return self.face_embedding is not None


def cosine(left: Any | None, right: Any | None) -> float | None:
    """职责：计算两个 L2 embedding 的 cosine；缺证据时返回 None。"""

    if left is None or right is None:
        return None
    import numpy as np

    a = np.asarray(left, dtype=np.float32).reshape(-1)
    b = np.asarray(right, dtype=np.float32).reshape(-1)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 1e-9:
        return None
    return float(np.dot(a, b) / denominator)


def mean_vector(values: list[Any]) -> Any | None:
    """职责：把一组 embedding 聚合成归一化中心向量。"""

    if not values:
        return None
    import numpy as np

    array = np.stack([np.asarray(value, dtype=np.float32).reshape(-1) for value in values])
    mean = array.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    return mean / norm if norm > 1e-9 else mean


def bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


def _point_inside(point: tuple[float, float], box: tuple[int, int, int, int]) -> bool:
    px, py = point
    x, y, w, h = box
    return x <= px <= x + w and y <= py <= y + h


def _clamp_box(box: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int] | None:
    x, y, w, h = box
    left = max(0, min(width - 1, int(round(x))))
    top = max(0, min(height - 1, int(round(y))))
    right = max(left + 1, min(width, int(round(x + w))))
    bottom = max(top + 1, min(height, int(round(y + h))))
    if right - left < 12 or bottom - top < 24:
        return None
    return left, top, right - left, bottom - top


def sample_ratios(duration_us: int) -> tuple[float, ...]:
    """按 Shot 时长决定采样数量。

    旧版固定 3 帧容易刚好错过转头/入画；V4 对正常 1~3 秒短剧 Shot 取 7 帧，
    长 Shot 取 9 帧，极短 Shot 自动减少，既提高 recall 又控制计算量。
    """

    if duration_us <= 450_000:
        return (0.10, 0.50, 0.90)
    if duration_us <= 900_000:
        return (0.08, 0.28, 0.50, 0.72, 0.92)
    if duration_us <= 2_500_000:
        return (0.05, 0.20, 0.35, 0.50, 0.65, 0.80, 0.95)
    return (0.04, 0.16, 0.28, 0.40, 0.50, 0.60, 0.72, 0.84, 0.96)


def _read_frames(reference_path: str, local_times_us: list[int]) -> list[tuple[int, Any]]:
    """一次打开 Reference Clip，按多个时间点读取帧，避免每帧重复打开 VideoCapture。"""

    import cv2

    capture = cv2.VideoCapture(reference_path)
    results: list[tuple[int, Any]] = []
    try:
        for local_us in local_times_us:
            capture.set(cv2.CAP_PROP_POS_MSEC, local_us / 1000.0)
            ok, frame = capture.read()
            if ok and frame is not None:
                results.append((local_us, frame))
    finally:
        capture.release()
    return results


def _read_frame(reference_path: str, local_time_us: int) -> Any | None:
    frames = _read_frames(reference_path, [local_time_us])
    return frames[0][1] if frames else None


def _body_histogram(frame: Any, body_bbox: tuple[int, int, int, int]) -> Any | None:
    """轻量服装颜色 Evidence，只做 ReID 的三级辅助，不再承担人物检测。"""

    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    x, y, w, h = body_bbox
    left, top = max(0, x), max(0, y)
    right, bottom = min(width, x + w), min(height, y + h)
    if right - left < 20 or bottom - top < 32:
        return None
    crop = frame[top:bottom, left:right]
    # 去掉头顶和最底部，降低背景与人脸肤色影响。
    top_offset = int(crop.shape[0] * 0.14)
    bottom_offset = int(crop.shape[0] * 0.08)
    crop = crop[top_offset : max(top_offset + 8, crop.shape[0] - bottom_offset)]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 12], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(hist))
    return hist / norm if norm > 1e-9 else None


def _synthetic_body_box(face_bbox: tuple[int, int, int, int], frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    """YOLOX 在纯脸部大特写漏掉 person 时，用高置信 Face 构造临时 person crop。"""

    x, y, w, h = face_bbox
    left = max(0, int(x - 0.9 * w))
    top = max(0, int(y - 0.25 * h))
    right = min(frame_width, int(x + 1.9 * w))
    bottom = min(frame_height, int(y + 5.4 * h))
    return left, top, max(1, right - left), max(1, bottom - top)


class _YoloXPersonDetector:
    """OpenCV Zoo YOLOX wrapper，只保留 COCO person(class=0)。"""

    def __init__(self, model_path: Path):
        import cv2
        import numpy as np

        self.cv2 = cv2
        self.np = np
        self.net = cv2.dnn.readNet(str(model_path))
        self.input_size = 640
        grids: list[Any] = []
        strides: list[Any] = []
        for stride in (8, 16, 32):
            size = self.input_size // stride
            xv, yv = np.meshgrid(np.arange(size), np.arange(size))
            grid = np.stack((xv, yv), axis=2).reshape(-1, 2).astype(np.float32)
            grids.append(grid)
            strides.append(np.full((grid.shape[0], 1), stride, dtype=np.float32))
        self.grids = np.concatenate(grids, axis=0)
        self.expanded_strides = np.concatenate(strides, axis=0)

    def _letterbox(self, frame: Any) -> tuple[Any, float]:
        cv2, np = self.cv2, self.np
        h, w = frame.shape[:2]
        ratio = min(self.input_size / max(1, h), self.input_size / max(1, w))
        resized = cv2.resize(frame, (max(1, int(w * ratio)), max(1, int(h * ratio))), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        canvas = np.full((self.input_size, self.input_size, 3), 114.0, dtype=np.float32)
        canvas[: rgb.shape[0], : rgb.shape[1]] = rgb
        return canvas, ratio

    def detect(self, frame: Any) -> list[tuple[tuple[int, int, int, int], float]]:
        cv2, np = self.cv2, self.np
        input_image, ratio = self._letterbox(frame)
        blob = np.transpose(input_image, (2, 0, 1))[None, :, :, :]
        self.net.setInput(blob)
        outputs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        raw = outputs[0]
        dets = raw[0].copy() if raw.ndim == 3 else raw.copy()
        if dets.ndim != 2 or dets.shape[0] != self.grids.shape[0] or dets.shape[1] < 6:
            return []
        dets[:, :2] = (dets[:, :2] + self.grids) * self.expanded_strides
        dets[:, 2:4] = np.exp(dets[:, 2:4]) * self.expanded_strides
        person_scores = dets[:, 4] * dets[:, 5]  # COCO class 0 = person
        mask = person_scores >= PERSON_SCORE_THRESHOLD
        if not np.any(mask):
            return []
        chosen = dets[mask]
        scores = person_scores[mask]
        boxes = np.empty((chosen.shape[0], 4), dtype=np.float32)
        boxes[:, 0] = chosen[:, 0] - chosen[:, 2] / 2.0
        boxes[:, 1] = chosen[:, 1] - chosen[:, 3] / 2.0
        boxes[:, 2] = chosen[:, 2]
        boxes[:, 3] = chosen[:, 3]
        keep = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), PERSON_SCORE_THRESHOLD, PERSON_NMS_THRESHOLD)
        if len(keep) == 0:
            return []
        height, width = frame.shape[:2]
        results: list[tuple[tuple[int, int, int, int], float]] = []
        for index in np.asarray(keep).reshape(-1):
            box = boxes[int(index)] / max(ratio, 1e-9)
            clamped = _clamp_box(tuple(float(value) for value in box), width, height)
            if clamped is None:
                continue
            results.append((clamped, float(scores[int(index)])))
        return results


class _YoutuReID:
    """OpenCV Zoo YoutuReID 768-d appearance embedding。"""

    def __init__(self, model_path: Path):
        import cv2

        self.cv2 = cv2
        self.net = cv2.dnn.readNet(str(model_path))

    def infer(self, frame: Any, bbox: tuple[int, int, int, int]) -> Any | None:
        cv2 = self.cv2
        import numpy as np

        height, width = frame.shape[:2]
        x, y, w, h = bbox
        pad_x, pad_y = int(w * 0.04), int(h * 0.025)
        left, top = max(0, x - pad_x), max(0, y - pad_y)
        right, bottom = min(width, x + w + pad_x), min(height, y + h + pad_y)
        crop = frame[top:bottom, left:right]
        if crop.size == 0 or crop.shape[0] < 24 or crop.shape[1] < 12:
            return None
        crop = cv2.resize(crop, (128, 256), interpolation=cv2.INTER_LINEAR)
        image = crop[:, :, ::-1].astype(np.float32) / 255.0
        mean = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
        std = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
        image = (image - mean) / std
        blob = cv2.dnn.blobFromImage(image.astype(np.float32))
        self.net.setInput(blob)
        feature = self.net.forward().reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feature))
        return feature / norm if norm > 1e-9 else None


def _face_embedding(recognizer: Any, frame: Any, row: Any) -> Any | None:
    import numpy as np

    try:
        aligned = recognizer.alignCrop(frame, row)
        feature = recognizer.feature(aligned).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feature))
        return feature / norm if norm > 1e-9 else None
    except Exception:
        return None


def detect_observations(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[Observation]:
    """对全部 Shot 产生 Person Observation。

    每个 YOLOX person 都会生成 Observation；Face 只是附加身份锚点。
    因此“检测到人但识别不出是谁”会继续进入 UNRESOLVED Evidence，而不是被丢弃。
    """

    import cv2

    models = require_models()
    face_detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]),
        "",
        (320, 320),
        score_threshold=FACE_DETECTION_THRESHOLD,
        nms_threshold=0.30,
        top_k=5000,
    )
    face_recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")
    person_detector = _YoloXPersonDetector(models["person_detection.yolox.2022nov"])
    reid = _YoutuReID(models["person_reid.youtu.2021nov"])

    observations: list[Observation] = []
    total = len(shots)
    for shot_index, shot in enumerate(shots, start=1):
        if progress:
            progress(shot_index, total, f"人物识别：Shot {shot_index} / {total}")
        duration_us = max(1, int(shot["duration_us"]))
        local_times = sorted({
            max(0, min(duration_us - 1, int(duration_us * ratio)))
            for ratio in sample_ratios(duration_us)
        })
        for local_us, frame in _read_frames(shot["reference_path"], local_times):
            height, width = frame.shape[:2]
            persons = person_detector.detect(frame)

            face_detector.setInputSize((width, height))
            _, face_rows = face_detector.detect(frame)
            faces: list[tuple[Any, tuple[int, int, int, int], float]] = []
            if face_rows is not None:
                for row in face_rows:
                    x, y, w, h = [int(round(float(value))) for value in row[:4]]
                    box = _clamp_box((x, y, w, h), width, height)
                    if box is None or box[2] < 18 or box[3] < 18:
                        continue
                    faces.append((row, box, float(row[-1])))

            used_faces: set[int] = set()
            # 先以 person 为主单位，再把最可信的 face 挂进对应 person。
            for person_box, person_score in sorted(persons, key=lambda item: item[1], reverse=True):
                matching: list[tuple[int, Any, tuple[int, int, int, int], float]] = []
                for face_index, (row, face_box, face_score) in enumerate(faces):
                    if face_index in used_faces:
                        continue
                    if _point_inside(_center(face_box), person_box):
                        matching.append((face_index, row, face_box, face_score))
                face_row = None
                face_box = None
                face_score = 0.0
                if matching:
                    # 同一个 person box 内优先最高脸分；近景多人重叠时 person NMS 已先处理。
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
                    face_embedding=_face_embedding(face_recognizer, frame, face_row) if face_row is not None else None,
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=_body_histogram(frame, person_box),
                    face_visible=face_row is not None,
                    detection_source="yolox+face" if face_row is not None else "yolox",
                ))

            # 纯大特写可能 YOLOX 没有完整 person box；高置信 Face 仍然不能被漏掉。
            for face_index, (row, face_box, face_score) in enumerate(faces):
                if face_index in used_faces or face_score < FACE_FALLBACK_THRESHOLD:
                    continue
                person_box = _synthetic_body_box(face_box, width, height)
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
                    face_embedding=_face_embedding(face_recognizer, frame, row),
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=_body_histogram(frame, person_box),
                    face_visible=True,
                    detection_source="face_fallback",
                ))
    return observations


def _track_match_score(track: TrackDraft, observation: Observation) -> float | None:
    """Shot 内 Track 匹配分；Face > ReID > 空间连续性 > 颜色。"""

    last = track.observations[-1]
    face_score = cosine(track.face_embedding, observation.face_embedding)
    reid_score = cosine(track.reid_embedding, observation.reid_embedding)
    body_score = cosine(track.body_hist, observation.body_hist)
    spatial = bbox_iou(last.bbox, observation.bbox)

    qualified = (
        (face_score is not None and face_score >= TRACK_FACE_THRESHOLD)
        or (reid_score is not None and reid_score >= TRACK_REID_THRESHOLD)
        or (reid_score is not None and reid_score >= TRACK_REID_SPATIAL_THRESHOLD and spatial >= 0.22)
    )
    if not qualified:
        return None
    return (
        max(0.0, face_score or 0.0) * 0.55
        + max(0.0, reid_score or 0.0) * 0.33
        + spatial * 0.09
        + max(0.0, body_score or 0.0) * 0.03
    )


def _refresh_track(track: TrackDraft) -> None:
    track.face_embedding = mean_vector([item.face_embedding for item in track.observations if item.face_embedding is not None])
    track.reid_embedding = mean_vector([item.reid_embedding for item in track.observations if item.reid_embedding is not None])
    track.body_hist = mean_vector([item.body_hist for item in track.observations if item.body_hist is not None])


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    """把同 Shot 不同采样帧的 Observation 一对一连接成 Track。

    同一帧采用全局贪心配对，避免第一个 Observation 更新 Track 后把同框第二个人也吞进去。
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
        result.extend(tracks)
    return result


def _candidate_track_similarity(candidate: CandidateDraft, track: TrackDraft) -> tuple[float | None, float | None, float | None]:
    face_scores = [cosine(member.face_embedding, track.face_embedding) for member in candidate.tracks]
    reid_scores = [cosine(member.reid_embedding, track.reid_embedding) for member in candidate.tracks]
    body_scores = [cosine(member.body_hist, track.body_hist) for member in candidate.tracks]
    face = max((value for value in face_scores if value is not None), default=None)
    reid = max((value for value in reid_scores if value is not None), default=None)
    body = max((value for value in body_scores if value is not None), default=None)
    return face, reid, body


def _candidate_gap(candidate: CandidateDraft, track: TrackDraft) -> int | None:
    gaps = [
        abs(member.shot_ordinal - track.shot_ordinal)
        for member in candidate.tracks
        if member.episode_id == track.episode_id
    ]
    return min(gaps) if gaps else None


def _append_track(candidate: CandidateDraft, track: TrackDraft, score: float | None = None) -> None:
    candidate.tracks.append(track)
    if score is not None:
        candidate.scores.append(score)
    candidate.face_embedding = mean_vector([member.face_embedding for member in candidate.tracks if member.face_embedding is not None])
    candidate.reid_embedding = mean_vector([member.reid_embedding for member in candidate.tracks if member.reid_embedding is not None])
    candidate.body_hist = mean_vector([member.body_hist for member in candidate.tracks if member.body_hist is not None])
    candidate.identity_status = "RESOLVED" if candidate.face_embedding is not None else "UNRESOLVED"


def _resolved_match_score(candidate: CandidateDraft, track: TrackDraft) -> float | None:
    if any(member.shot_id == track.shot_id for member in candidate.tracks):
        return None
    face, reid, body = _candidate_track_similarity(candidate, track)
    gap = _candidate_gap(candidate, track)
    strong_face = face is not None and face >= FACE_STRONG_MATCH
    supported_face = (
        face is not None
        and face >= FACE_SUPPORTED_MATCH
        and (
            (reid is not None and reid >= CANDIDATE_REID_SUPPORT)
            or (gap is not None and gap <= 3 and face >= 0.40)
        )
    )
    if not (strong_face or supported_face):
        return None
    temporal_bonus = 0.04 if gap is not None and gap <= 2 else 0.0
    return (
        max(0.0, face or 0.0) * 0.72
        + max(0.0, reid or 0.0) * 0.22
        + max(0.0, body or 0.0) * 0.02
        + temporal_bonus
    )


def _merge_candidate_into(target: CandidateDraft, source: CandidateDraft, score: float) -> None:
    for track in source.tracks:
        _append_track(target, track, score)


def _merge_resolved_fragments(candidates: list[CandidateDraft]) -> list[CandidateDraft]:
    """二次去碎片：解决 greedy 顺序聚类把同一演员拆成多个 Face Candidate。"""

    changed = True
    while changed:
        changed = False
        best_pair: tuple[float, int, int] | None = None
        for left_index in range(len(candidates)):
            left = candidates[left_index]
            if not left.has_face_anchor:
                continue
            for right_index in range(left_index + 1, len(candidates)):
                right = candidates[right_index]
                if not right.has_face_anchor:
                    continue
                if {item.shot_id for item in left.tracks} & {item.shot_id for item in right.tracks}:
                    continue
                face_scores = [
                    cosine(a.face_embedding, b.face_embedding)
                    for a in left.tracks for b in right.tracks
                    if a.face_embedding is not None and b.face_embedding is not None
                ]
                reid_scores = [
                    cosine(a.reid_embedding, b.reid_embedding)
                    for a in left.tracks for b in right.tracks
                    if a.reid_embedding is not None and b.reid_embedding is not None
                ]
                face = max((value for value in face_scores if value is not None), default=None)
                reid = max((value for value in reid_scores if value is not None), default=None)
                qualifies = bool(
                    face is not None
                    and (
                        face >= 0.52
                        or (face >= 0.40 and reid is not None and reid >= 0.64)
                    )
                )
                if not qualifies:
                    continue
                score = (face or 0.0) * 0.78 + (reid or 0.0) * 0.22
                if best_pair is None or score > best_pair[0]:
                    best_pair = (score, left_index, right_index)
        if best_pair is not None:
            score, left_index, right_index = best_pair
            _merge_candidate_into(candidates[left_index], candidates[right_index], score)
            del candidates[right_index]
            changed = True
    return candidates


def cluster_candidates(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    """跨 Shot 聚类。

    1. Face Track 建立 RESOLVED identity；
    2. 二次合并 Face fragment；
    3. body-only 通过专用 YoutuReID 挂回已有 identity；
    4. 挂不回去的 person 仍保留 UNRESOLVED Evidence，不创建 Final Character。
    """

    ordered = sorted(tracks, key=lambda item: (item.episode_order, item.shot_ordinal))
    face_tracks = [track for track in ordered if track.face_embedding is not None]
    body_only_tracks = [track for track in ordered if track.face_embedding is None]
    resolved: list[CandidateDraft] = []

    for track in face_tracks:
        best: CandidateDraft | None = None
        best_score = -1.0
        for candidate in resolved:
            score = _resolved_match_score(candidate, track)
            if score is not None and score > best_score:
                best, best_score = candidate, score
        if best is None:
            best = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="RESOLVED")
            resolved.append(best)
            _append_track(best, track)
        else:
            _append_track(best, track, best_score)

    resolved = _merge_resolved_fragments(resolved)
    unresolved: list[CandidateDraft] = []

    for track in body_only_tracks:
        best_resolved: CandidateDraft | None = None
        best_score = -1.0
        for candidate in resolved:
            if any(member.shot_id == track.shot_id for member in candidate.tracks):
                continue
            _face, reid, body = _candidate_track_similarity(candidate, track)
            gap = _candidate_gap(candidate, track)
            if reid is None:
                continue
            qualifies = (
                (gap is not None and gap <= MAX_BODY_ATTACH_GAP and reid >= RESOLVED_REID_THRESHOLD)
                or (gap is not None and gap <= 1 and reid >= 0.64 and (body or 0.0) >= 0.74)
            )
            if not qualifies:
                continue
            score = reid * 0.92 + max(0.0, body or 0.0) * 0.08
            if score > best_score:
                best_resolved, best_score = candidate, score
        if best_resolved is not None:
            _append_track(best_resolved, track, best_score)
            continue

        # 明确检测到 Person 但身份还无法解析：保留 Evidence，而不是静默丢弃。
        best_unresolved: CandidateDraft | None = None
        best_unresolved_score = -1.0
        for candidate in unresolved:
            if any(member.shot_id == track.shot_id for member in candidate.tracks):
                continue
            _face, reid, _body = _candidate_track_similarity(candidate, track)
            gap = _candidate_gap(candidate, track)
            if reid is None or gap is None or gap > MAX_UNRESOLVED_CLUSTER_GAP or reid < UNRESOLVED_REID_THRESHOLD:
                continue
            if reid > best_unresolved_score:
                best_unresolved, best_unresolved_score = candidate, reid
        if best_unresolved is None:
            best_unresolved = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
            unresolved.append(best_unresolved)
            _append_track(best_unresolved, track)
        else:
            _append_track(best_unresolved, track, best_unresolved_score)

    return resolved + unresolved


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[CandidateDraft]:
    """人物 V4 总入口：Person Detection → Track → Identity Clustering。"""

    return cluster_candidates(build_tracks(detect_observations(shots, progress=progress)))


def candidate_confidence(candidate: CandidateDraft) -> float | None:
    """给 UI 一个可解释的候选置信度；UNRESOLVED 不冒充身份置信度。"""

    if candidate.identity_status == "UNRESOLVED":
        detections = [obs.detection_score for track in candidate.tracks for obs in track.observations]
        return min(0.69, sum(detections) / len(detections)) if detections else 0.50
    if candidate.scores:
        return max(0.0, min(1.0, sum(candidate.scores) / len(candidate.scores)))
    face_scores = [
        obs.detection_score
        for track in candidate.tracks
        for obs in track.observations
        if obs.face_visible
    ]
    return min(0.95, sum(face_scores) / len(face_scores)) if face_scores else None


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    """保存 Evidence 封面；RESOLVED 优先露脸，UNRESOLVED 取最高 Person Detection。"""

    import cv2

    observations = [item for track in candidate.tracks for item in track.observations]
    if not observations:
        return None
    representative = max(
        observations,
        key=lambda item: (
            1 if candidate.identity_status == "RESOLVED" and item.face_visible else 0,
            item.detection_score,
        ),
    )
    frame = _read_frame(representative.reference_path, representative.local_time_us)
    if frame is None:
        return None
    x, y, w, h = representative.bbox
    height, width = frame.shape[:2]
    pad_x, pad_y = int(w * 0.08), int(h * 0.04)
    left, top = max(0, x - pad_x), max(0, y - pad_y)
    right, bottom = min(width, x + w + pad_x), min(height, y + h + pad_y)
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    path = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path) if cv2.imwrite(str(path), crop) else None
