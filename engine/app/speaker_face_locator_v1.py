"""R10 target-speaker face locator for safe multi-person lip sync.

LatentSync 1.6 cannot be trusted to choose the intended person when several faces are visible.
This module reuses the project's already-approved YuNet + SFace stack to identify the current
TargetCharacter against its current H3 casting-reference images. It is intentionally fail-closed:
no unique repeated target face -> no automatic crop/lip-sync.
"""
from __future__ import annotations

from statistics import median
from pathlib import Path
from typing import Any, Mapping

from engine.app.character_visual_v4 import cosine, mean_vector
from engine.app.content_models_v2 import RequiredCharacterModelError, require_models
from engine.app.h3_reference_assets_v1 import current_target_character_reference_assets_v1


FACE_DETECTION_THRESHOLD = 0.76
TARGET_MATCH_MIN = 0.38
TARGET_MATCH_MEDIAN_MIN = 0.42
TARGET_WINNER_MARGIN = 0.07
MAX_SAMPLE_COUNT = 12


class SpeakerFaceLocatorError(RuntimeError):
    pass


def _clamp_box(box: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int] | None:
    x, y, w, h = box
    left = max(0, min(width - 1, int(round(x))))
    top = max(0, min(height - 1, int(round(y))))
    right = max(left + 1, min(width, int(round(x + w))))
    bottom = max(top + 1, min(height, int(round(y + h))))
    if right - left < 24 or bottom - top < 24:
        return None
    # H.264 crop/composite paths are more predictable with even dimensions.
    right -= (right - left) % 2
    bottom -= (bottom - top) % 2
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def _face_embedding(recognizer: Any, frame: Any, row: Any) -> Any | None:
    import numpy as np

    try:
        aligned = recognizer.alignCrop(frame, row)
        feature = recognizer.feature(aligned).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feature))
        return feature / norm if norm > 1e-9 else None
    except Exception:
        return None


def _make_models() -> tuple[Any, Any]:
    import cv2

    models = require_models()
    detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]),
        "",
        (320, 320),
        score_threshold=FACE_DETECTION_THRESHOLD,
        nms_threshold=0.30,
        top_k=5000,
    )
    recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")
    return detector, recognizer


def _faces(detector: Any, recognizer: Any, frame: Any) -> list[dict[str, Any]]:
    height, width = frame.shape[:2]
    detector.setInputSize((width, height))
    _ok, rows = detector.detect(frame)
    result: list[dict[str, Any]] = []
    if rows is None:
        return result
    for row in rows:
        box = _clamp_box(tuple(float(value) for value in row[:4]), width, height)
        if box is None or box[2] < 20 or box[3] < 20:
            continue
        embedding = _face_embedding(recognizer, frame, row)
        if embedding is None:
            continue
        result.append({"box": box, "score": float(row[-1]), "embedding": embedding})
    return result


def _reference_embedding(character: Mapping[str, Any], detector: Any, recognizer: Any) -> Any | None:
    import cv2

    embeddings: list[Any] = []
    for path in current_target_character_reference_assets_v1(character):
        image = cv2.imread(str(path))
        if image is None or image.size == 0:
            continue
        faces = _faces(detector, recognizer, image)
        if not faces:
            continue
        # Casting references are generated with exactly one person. If generation still produced
        # several detections, use the clearest/largest face only and require agreement across refs.
        best = max(faces, key=lambda item: item["score"] * max(1, item["box"][2] * item["box"][3]))
        embeddings.append(best["embedding"])
    return mean_vector(embeddings)


def _sample_times(windows: list[tuple[int, int]], duration_us: int) -> list[int]:
    values: list[int] = []
    for start, end in windows:
        left = max(0, min(duration_us - 1, int(start)))
        right = max(left + 1, min(duration_us, int(end)))
        width = right - left
        count = 3 if width < 900_000 else 5
        for index in range(count):
            ratio = (index + 0.5) / count
            values.append(max(0, min(duration_us - 1, int(round(left + width * ratio)))))
    unique = sorted(set(values))
    if len(unique) <= MAX_SAMPLE_COUNT:
        return unique
    step = (len(unique) - 1) / (MAX_SAMPLE_COUNT - 1)
    return [unique[int(round(index * step))] for index in range(MAX_SAMPLE_COUNT)]


def _contains(box: tuple[int, int, int, int], point: tuple[float, float]) -> bool:
    x, y, w, h = box
    px, py = point
    return x <= px <= x + w and y <= py <= y + h


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


def _safe_fixed_roi(
    target_boxes: list[tuple[int, int, int, int]],
    other_boxes: list[tuple[int, int, int, int]],
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    if not target_boxes:
        return None
    left = min(box[0] for box in target_boxes)
    top = min(box[1] for box in target_boxes)
    right = max(box[0] + box[2] for box in target_boxes)
    bottom = max(box[1] + box[3] for box in target_boxes)
    face_w = max(box[2] for box in target_boxes)
    face_h = max(box[3] for box in target_boxes)
    # Include hair/chin/cheeks around all sampled target positions, but stay compact enough that a
    # nearby second actor is not silently handed to LatentSync as another candidate face.
    raw = (
        left - face_w * 0.85,
        top - face_h * 0.75,
        (right - left) + face_w * 1.70,
        (bottom - top) + face_h * 1.65,
    )
    roi = _clamp_box(raw, width, height)
    if roi is None:
        return None
    if roi[2] * roi[3] > width * height * 0.72:
        return None
    if any(_contains(roi, _center(box)) for box in other_boxes):
        return None
    return roi


def locate_target_speaker_face_v1(
    *,
    video_path: Path,
    target_character: Mapping[str, Any],
    windows: list[tuple[int, int]],
    duration_us: int,
) -> dict[str, Any]:
    """Locate one target face repeatedly and return a safe fixed ROI for LatentSync.

    `windows` are segment-local visible-dialogue intervals. The function only samples those windows;
    it never infers who is speaking from lip motion and never substitutes source-actor identity.
    """

    source = video_path.expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise SpeakerFaceLocatorError("Selected Output 不存在，无法定位目标说话人")
    if not windows:
        return {"status": "REVIEW", "reason": "没有可见对白窗口可用于目标说话人定位"}
    try:
        detector, recognizer = _make_models()
    except RequiredCharacterModelError as exc:
        return {"status": "WAITING_MODEL", "reason": str(exc)}
    reference = _reference_embedding(target_character, detector, recognizer)
    if reference is None:
        return {"status": "WAITING_REFERENCE", "reason": "当前 TargetCharacter 参考图没有可用 SFace 身份锚点"}

    import cv2

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise SpeakerFaceLocatorError("Selected Output 无法打开")
    sample_times = _sample_times(windows, duration_us)
    accepted: list[dict[str, Any]] = []
    frame_width = 0
    frame_height = 0
    try:
        for local_us in sample_times:
            capture.set(cv2.CAP_PROP_POS_MSEC, local_us / 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            frame_height, frame_width = frame.shape[:2]
            faces = _faces(detector, recognizer, frame)
            scored = sorted(
                [
                    {**item, "similarity": cosine(reference, item["embedding"])}
                    for item in faces
                ],
                key=lambda item: float(item["similarity"] if item["similarity"] is not None else -1.0),
                reverse=True,
            )
            if not scored or scored[0]["similarity"] is None:
                continue
            winner = scored[0]
            winner_score = float(winner["similarity"])
            second_score = (
                float(scored[1]["similarity"])
                if len(scored) > 1 and scored[1]["similarity"] is not None
                else None
            )
            margin = winner_score - second_score if second_score is not None else 1.0
            if winner_score < TARGET_MATCH_MIN or margin < TARGET_WINNER_MARGIN:
                continue
            accepted.append({
                "time_us": local_us,
                "box": winner["box"],
                "similarity": winner_score,
                "margin": margin,
                "other_boxes": [item["box"] for item in scored[1:]],
            })
    finally:
        capture.release()

    support_needed = min(3, max(2, len(sample_times)))
    if len(accepted) < support_needed:
        return {
            "status": "REVIEW",
            "reason": f"目标说话人 SFace 唯一匹配只在 {len(accepted)}/{len(sample_times)} 个采样点成立",
            "support_count": len(accepted),
            "sample_count": len(sample_times),
        }
    scores = [float(item["similarity"]) for item in accepted]
    median_score = float(median(scores))
    if median_score < TARGET_MATCH_MEDIAN_MIN:
        return {
            "status": "REVIEW",
            "reason": f"目标说话人 SFace 中位相似度不足：{median_score:.3f}",
            "support_count": len(accepted),
            "sample_count": len(sample_times),
            "median_similarity": median_score,
        }
    target_boxes = [tuple(item["box"]) for item in accepted]
    other_boxes = [tuple(box) for item in accepted for box in item["other_boxes"]]
    roi = _safe_fixed_roi(target_boxes, other_boxes, frame_width, frame_height)
    if roi is None:
        return {
            "status": "REVIEW",
            "reason": "虽然识别到目标说话人，但无法形成不包含其他人脸的安全固定口型 ROI",
            "support_count": len(accepted),
            "sample_count": len(sample_times),
            "median_similarity": median_score,
        }
    return {
        "status": "READY",
        "reason": "目标说话人已通过当前 TargetCharacter 参考图重复唯一匹配",
        "crop_box": list(roi),
        "support_count": len(accepted),
        "sample_count": len(sample_times),
        "median_similarity": median_score,
        "minimum_margin": min(float(item["margin"]) for item in accepted),
        "sample_times_us": [int(item["time_us"]) for item in accepted],
    }


__all__ = [
    "SpeakerFaceLocatorError",
    "locate_target_speaker_face_v1",
]
