"""F05 V2 人物视觉 Evidence。

职责：
- YuNet 检测人脸；
- SFace 生成身份 embedding；
- OpenCV HOG / 合成人体框补充身体与服装 Evidence；
- Shot 内 Track；
- 跨 Shot 保守 Character Candidate 聚类。

核心规则：
- 人物 != 人脸，所以身体 / 服装 Evidence 必须保留；
- 但 HOG body-only 误检率不足以单独证明“这是一个人物身份”；
- 正式 Character Candidate 必须至少拥有一个 Face/SFace 身份锚点；
- body-only Track 只能在相邻 Shot 且身体 Evidence 极高相似时挂回已有的 face-anchored Candidate；
- 同一 Shot 同时出现的两个 Track 永远不能自动合成同一个 Candidate。

为什么这样改：
旧版允许任何 body-only Track 自己创建 Candidate，真实短剧中 HOG 会把花、衣服、背景纹理等误检为人体，
最终产生上千个单镜头“人物”。身体 Evidence 应该是辅助身份连续性的证据，而不是独立身份 Source of Truth。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any

from engine.app.content_models_v2 import require_models
from engine.app.studio_v2 import new_id, workspace_root

SAMPLE_RATIOS = (0.18, 0.50, 0.82)
FACE_SCORE_THRESHOLD = 0.90
TRACK_FACE_THRESHOLD = 0.38
TRACK_BODY_THRESHOLD = 0.93
FACE_CLUSTER_THRESHOLD = 0.45
BODY_ONLY_CLUSTER_THRESHOLD = 0.985
MAX_HOG_WIDTH = 720


@dataclass
class Observation:
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
    body_hist: Any | None
    face_visible: bool


@dataclass
class TrackDraft:
    shot_id: str
    episode_id: str
    episode_order: int
    shot_ordinal: int
    observations: list[Observation] = field(default_factory=list)
    face_embedding: Any | None = None
    body_hist: Any | None = None


@dataclass
class CandidateDraft:
    id: str
    tracks: list[TrackDraft] = field(default_factory=list)
    face_embedding: Any | None = None
    body_hist: Any | None = None
    scores: list[float] = field(default_factory=list)


def cosine(left: Any | None, right: Any | None) -> float | None:
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


def _read_frame(reference_path: str, local_time_us: int) -> Any | None:
    import cv2

    capture = cv2.VideoCapture(reference_path)
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, local_time_us / 1000.0)
        ok, frame = capture.read()
        return frame if ok else None
    finally:
        capture.release()


def _body_histogram(frame: Any, body_bbox: tuple[int, int, int, int]) -> Any | None:
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    x, y, w, h = body_bbox
    left, top = max(0, x), max(0, y)
    right, bottom = min(width, x + w), min(height, y + h)
    if right - left < 20 or bottom - top < 32:
        return None
    crop = frame[top:bottom, left:right]
    # 去掉人物最上方约 15%，降低人脸肤色对 body descriptor 的权重。
    offset = int(crop.shape[0] * 0.15)
    crop = crop[offset:] if offset < crop.shape[0] - 8 else crop
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 12], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(hist))
    return hist / norm if norm > 1e-9 else None


def _synthetic_body_box(face_bbox: tuple[int, int, int, int], frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    x, y, w, h = face_bbox
    left = max(0, int(x - 0.8 * w))
    top = max(0, int(y - 0.2 * h))
    right = min(frame_width, int(x + 1.8 * w))
    bottom = min(frame_height, int(y + 5.2 * h))
    return left, top, max(1, right - left), max(1, bottom - top)


def _detect_bodies(frame: Any, hog: Any) -> list[tuple[tuple[int, int, int, int], float]]:
    import cv2

    height, width = frame.shape[:2]
    scale = min(1.0, MAX_HOG_WIDTH / max(1, width))
    if scale < 1.0:
        resized = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    else:
        resized = frame
    rects, weights = hog.detectMultiScale(
        resized,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
        hitThreshold=0.0,
    )
    results: list[tuple[tuple[int, int, int, int], float]] = []
    inverse = 1.0 / scale
    for rect, raw_weight in zip(rects, weights):
        x, y, w, h = [int(round(float(value) * inverse)) for value in rect]
        weight = float(raw_weight)
        if w < 35 or h < 70:
            continue
        # HOG weight 不是真正概率，这里只做 0..1 Evidence 分数归一化。
        score = 1.0 / (1.0 + math.exp(-weight))
        results.append(((max(0, x), max(0, y), min(width - max(0, x), w), min(height - max(0, y), h)), score))
    return results


def detect_observations(shots: list[dict[str, Any]]) -> list[Observation]:
    import cv2
    import numpy as np

    models = require_models()
    detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]),
        "",
        (320, 320),
        score_threshold=FACE_SCORE_THRESHOLD,
        nms_threshold=0.30,
        top_k=5000,
    )
    recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    observations: list[Observation] = []
    for shot in shots:
        duration_us = int(shot["duration_us"])
        for ratio in SAMPLE_RATIOS:
            local_us = max(0, min(duration_us - 1, int(duration_us * ratio)))
            frame = _read_frame(shot["reference_path"], local_us)
            if frame is None:
                continue
            height, width = frame.shape[:2]
            bodies = _detect_bodies(frame, hog)
            used_body_indexes: set[int] = set()

            detector.setInputSize((width, height))
            _, faces = detector.detect(frame)
            if faces is not None:
                for row in faces:
                    x, y, w, h = [int(round(float(value))) for value in row[:4]]
                    if w < 28 or h < 28:
                        continue
                    x, y = max(0, x), max(0, y)
                    w, h = min(width - x, w), min(height - y, h)
                    if w <= 0 or h <= 0:
                        continue
                    face_box = (x, y, w, h)
                    face_center = _center(face_box)
                    body_box = None
                    body_index = None
                    matching = [
                        (index, box, score) for index, (box, score) in enumerate(bodies)
                        if _point_inside(face_center, box)
                    ]
                    if matching:
                        body_index, body_box, _ = min(matching, key=lambda item: item[1][2] * item[1][3])
                        used_body_indexes.add(body_index)
                    if body_box is None:
                        body_box = _synthetic_body_box(face_box, width, height)

                    try:
                        aligned = recognizer.alignCrop(frame, row)
                        feature = recognizer.feature(aligned).reshape(-1).astype(np.float32)
                        norm = float(np.linalg.norm(feature))
                        embedding = feature / norm if norm > 1e-9 else None
                    except Exception:
                        embedding = None
                    observations.append(Observation(
                        shot_id=shot["id"], episode_id=shot["episode_id"], episode_order=shot["episode_order"],
                        shot_ordinal=shot["ordinal"], source_time_us=shot["start_us"] + local_us,
                        local_time_us=local_us, bbox=body_box, face_bbox=face_box,
                        reference_path=shot["reference_path"], detection_score=float(row[-1]),
                        face_embedding=embedding, body_hist=_body_histogram(frame, body_box), face_visible=True,
                    ))

            # 未被 Face 命中的 HOG Person 只作为 body-only Evidence。
            # 它之后只能挂回已有 face-anchored Candidate，不能自己生成正式人物身份。
            for index, (body_box, body_score) in enumerate(bodies):
                if index in used_body_indexes:
                    continue
                observations.append(Observation(
                    shot_id=shot["id"], episode_id=shot["episode_id"], episode_order=shot["episode_order"],
                    shot_ordinal=shot["ordinal"], source_time_us=shot["start_us"] + local_us,
                    local_time_us=local_us, bbox=body_box, face_bbox=None,
                    reference_path=shot["reference_path"], detection_score=body_score,
                    face_embedding=None, body_hist=_body_histogram(frame, body_box), face_visible=False,
                ))
    return observations


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    by_shot: dict[str, list[Observation]] = {}
    for item in observations:
        by_shot.setdefault(item.shot_id, []).append(item)

    result: list[TrackDraft] = []
    for shot_observations in by_shot.values():
        tracks: list[TrackDraft] = []
        for observation in sorted(shot_observations, key=lambda item: (item.source_time_us, -item.detection_score)):
            best: TrackDraft | None = None
            best_score = -1.0
            for track in tracks:
                last = track.observations[-1]
                if observation.source_time_us == last.source_time_us:
                    continue
                face_score = cosine(track.face_embedding, observation.face_embedding)
                body_score = cosine(track.body_hist, observation.body_hist)
                spatial = bbox_iou(last.bbox, observation.bbox)
                qualifies = (face_score is not None and face_score >= TRACK_FACE_THRESHOLD) or (
                    body_score is not None and body_score >= TRACK_BODY_THRESHOLD and spatial >= 0.01
                )
                if not qualifies:
                    continue
                score = (face_score or 0.0) * 0.80 + (body_score or 0.0) * 0.15 + spatial * 0.05
                if score > best_score:
                    best, best_score = track, score
            if best is None:
                best = TrackDraft(
                    shot_id=observation.shot_id,
                    episode_id=observation.episode_id,
                    episode_order=observation.episode_order,
                    shot_ordinal=observation.shot_ordinal,
                )
                tracks.append(best)
            best.observations.append(observation)
            best.face_embedding = mean_vector([item.face_embedding for item in best.observations if item.face_embedding is not None])
            best.body_hist = mean_vector([item.body_hist for item in best.observations if item.body_hist is not None])
        result.extend(tracks)
    return result


def _append_track(candidate: CandidateDraft, track: TrackDraft, score: float | None = None) -> None:
    """把 Track 追加到 Candidate，并重算 face/body 聚合 Evidence。"""

    candidate.tracks.append(track)
    if score is not None:
        candidate.scores.append(score)
    candidate.face_embedding = mean_vector([member.face_embedding for member in candidate.tracks if member.face_embedding is not None])
    candidate.body_hist = mean_vector([member.body_hist for member in candidate.tracks if member.body_hist is not None])


def cluster_candidates(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    """把 Track 聚成 Character Candidate，但只有 Face/SFace Track 可以创建身份锚点。

    第 1 轮：先处理有 face embedding 的 Track，它们可以创建/合并正式身份。
    第 2 轮：再处理 body-only Track；只能以极高身体相似度连接到相邻 Shot 的已有身份，不能新建 Candidate。

    这样既保留背影/未露脸时的身体连续性，又不会让 HOG 的背景误检膨胀成成千上万个人物。
    """

    ordered = sorted(tracks, key=lambda item: (item.episode_order, item.shot_ordinal))
    face_tracks = [track for track in ordered if track.face_embedding is not None]
    body_only_tracks = [track for track in ordered if track.face_embedding is None]
    candidates: list[CandidateDraft] = []

    # 1) Face/SFace 是身份锚点。
    for track in face_tracks:
        best: CandidateDraft | None = None
        best_score = -1.0
        for candidate in candidates:
            # 同一 Shot 同框出现的两个 Track 不能自动认成同一个人。
            if any(member.shot_id == track.shot_id for member in candidate.tracks):
                continue
            face_score = cosine(candidate.face_embedding, track.face_embedding)
            if face_score is None or face_score < FACE_CLUSTER_THRESHOLD:
                continue
            body_score = cosine(candidate.body_hist, track.body_hist)
            score = face_score * 0.88 + (body_score or 0.0) * 0.12
            if score > best_score:
                best, best_score = candidate, score
        if best is None:
            best = CandidateDraft(id=new_id("CHAR_CANDIDATE"))
            candidates.append(best)
            _append_track(best, track)
        else:
            _append_track(best, track, best_score)

    # 2) body-only 只能挂回已有 face identity，绝不单独创建 Candidate。
    for track in body_only_tracks:
        best: CandidateDraft | None = None
        best_score = -1.0
        for candidate in candidates:
            if any(member.shot_id == track.shot_id for member in candidate.tracks):
                continue
            body_score = cosine(candidate.body_hist, track.body_hist)
            if body_score is None or body_score < BODY_ONLY_CLUSTER_THRESHOLD:
                continue
            adjacent = any(
                member.episode_id == track.episode_id
                and abs(member.shot_ordinal - track.shot_ordinal) <= 1
                for member in candidate.tracks
            )
            if not adjacent:
                continue
            if body_score > best_score:
                best, best_score = candidate, body_score
        if best is not None:
            _append_track(best, track, best_score)

    return candidates


def analyze_characters(shots: list[dict[str, Any]]) -> list[CandidateDraft]:
    return cluster_candidates(build_tracks(detect_observations(shots)))


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    import cv2

    observations = [item for track in candidate.tracks for item in track.observations]
    if not observations:
        return None
    # 正式 Candidate 一定有 Face/SFace 锚点；封面优先取露脸且检测分最高的 Observation。
    representative = max(observations, key=lambda item: (1 if item.face_visible else 0, item.detection_score))
    frame = _read_frame(representative.reference_path, representative.local_time_us)
    if frame is None:
        return None
    x, y, w, h = representative.bbox
    height, width = frame.shape[:2]
    pad_x, pad_y = int(w * 0.10), int(h * 0.05)
    left, top = max(0, x - pad_x), max(0, y - pad_y)
    right, bottom = min(width, x + w + pad_x), min(height, y + h + pad_y)
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    path = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path) if cv2.imwrite(str(path), crop) else None
