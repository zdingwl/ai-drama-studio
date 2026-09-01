"""Character V6.2 Person Observation。

职责：
- 复用已校验的 YOLOX Person / YoutuReID / YuNet / SFace 模型；
- Shot 内约 12fps 采样，为成熟 MOT 提供连续轨迹；
- 正常 Person 继续使用正式阈值；贴边、截断、无头近景允许以低分 partial-person proposal 进入 MOT；
- 全帧没有正常 Person 时，对左右边缘做放大重检，补救只剩肩背/躯干/手臂的近景；
- partial-person 即使碰巧检测到 Face，也必须保留 partial 来源，只能作为挂回已有身份的辅助 Evidence，
  不能伪装成普通 Face Track 去创建新的 Final Character；
- 大特写 Person Detector 失败时仍保留高置信 Face fallback。

这里只负责“这个时刻画面里有谁的视觉观测”，不创建 Character_ID。
"""
from __future__ import annotations

import math
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.character_visual_gpu_v41 import _YoloXOrtPersonDetector, _YoutuReIDOrt, _runtime_label
from engine.app.content_models_v2 import require_models

CharacterProgress = v5.CharacterProgress
Observation = v5.Observation

V6_SAMPLE_FPS = 12.0
V6_MIN_SAMPLES = 4
V6_MAX_SAMPLES = 60

# 正常 Person 不变；只有局部/截断人体走更低的 proposal 阈值，并由后续时序层确认。
STRONG_PERSON_SCORE = float(v5.legacy.PERSON_SCORE_THRESHOLD)
PARTIAL_PERSON_SCORE = 0.10
PARTIAL_MIN_AREA_RATIO = 0.020
PARTIAL_SUBSTANTIAL_AREA_RATIO = 0.060
PARTIAL_MIN_WIDTH_RATIO = 0.045
PARTIAL_MIN_HEIGHT_RATIO = 0.140
PARTIAL_EDGE_MARGIN_RATIO = 0.035

# 只有全帧没有正常 Person 时才补两次边缘放大推理，避免所有帧固定 3x 成本。
EDGE_RETRY_WIDTH_RATIO = 0.68
EDGE_RETRY_DEDUP_IOU = 0.55

# YOLOX can emit a high-confidence substantial Person box together with several
# very-low-confidence edge/body-part boxes for the same seated or close-up person.
# IoU alone does not remove those fragments because a narrow sleeve/head strip can be
# mostly covered by the substantial box while contributing little to the union area.
# Suppress only weak partial proposals that are mostly covered by an already-selected
# strong proposal. Two strong people and weak proposals with genuinely distinct
# visible area remain separate.
PARTIAL_FRAGMENT_MAX_SCORE = 0.20
PARTIAL_FRAGMENT_STRONG_COVERAGE = 0.65


def sample_times_us(duration_us: int) -> tuple[int, ...]:
    duration = max(1, int(duration_us))
    seconds = duration / 1_000_000.0
    count = max(V6_MIN_SAMPLES, int(math.ceil(seconds * V6_SAMPLE_FPS)) + 1)
    count = min(V6_MAX_SAMPLES, count)
    start = min(duration - 1, max(0, int(duration * 0.015)))
    end = min(duration - 1, max(start, int(duration * 0.985)))
    if count <= 1:
        return (duration // 2,)
    step = (end - start) / max(1, count - 1)
    return tuple(sorted({max(0, min(duration - 1, int(round(start + step * index)))) for index in range(count)}))


def _partial_person_box_plausible(
    box: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
) -> bool:
    """只让“像局部人体”的低分框进入时序确认，避免全局降阈值放大背景误检。"""

    width = max(1, int(frame_width))
    height = max(1, int(frame_height))
    x, y, w, h = box
    area_ratio = max(0.0, (w * h) / float(width * height))
    width_ratio = w / float(width)
    height_ratio = h / float(height)
    if area_ratio < PARTIAL_MIN_AREA_RATIO:
        return False
    if width_ratio < PARTIAL_MIN_WIDTH_RATIO and height_ratio < PARTIAL_MIN_HEIGHT_RATIO:
        return False

    margin_x = max(2, int(round(width * PARTIAL_EDGE_MARGIN_RATIO)))
    margin_y = max(2, int(round(height * PARTIAL_EDGE_MARGIN_RATIO)))
    touches_edge = (
        x <= margin_x
        or y <= margin_y
        or x + w >= width - margin_x
        or y + h >= height - margin_y
    )
    return touches_edge or area_ratio >= PARTIAL_SUBSTANTIAL_AREA_RATIO


def _detect_person_proposals(
    detector: _YoloXOrtPersonDetector,
    frame: Any,
    *,
    score_threshold: float,
) -> list[tuple[tuple[int, int, int, int], float]]:
    """一次 YOLOX forward 保留低分 person proposals；正式 V4.1 detector 默认阈值保持不变。"""

    cv2, np = detector.cv2, detector.np
    tensor, ratio = detector._letterbox(frame)
    outputs = detector.session.run(None, {detector.input_name: tensor})
    if not outputs:
        return []
    raw = np.asarray(outputs[0])
    dets = raw[0].copy() if raw.ndim == 3 else raw.copy()
    if dets.ndim != 2 or dets.shape[0] != detector.grids.shape[0] or dets.shape[1] < 6:
        return []

    dets[:, :2] = (dets[:, :2] + detector.grids) * detector.expanded_strides
    dets[:, 2:4] = np.exp(dets[:, 2:4]) * detector.expanded_strides
    person_scores = dets[:, 4] * dets[:, 5]
    mask = person_scores >= float(score_threshold)
    if not np.any(mask):
        return []

    chosen = dets[mask]
    scores = person_scores[mask]
    boxes = np.empty((chosen.shape[0], 4), dtype=np.float32)
    boxes[:, 0] = chosen[:, 0] - chosen[:, 2] / 2.0
    boxes[:, 1] = chosen[:, 1] - chosen[:, 3] / 2.0
    boxes[:, 2] = chosen[:, 2]
    boxes[:, 3] = chosen[:, 3]
    keep = cv2.dnn.NMSBoxes(
        boxes.tolist(),
        scores.tolist(),
        float(score_threshold),
        v5.legacy.PERSON_NMS_THRESHOLD,
    )
    if len(keep) == 0:
        return []

    height, width = frame.shape[:2]
    result: list[tuple[tuple[int, int, int, int], float]] = []
    for index in np.asarray(keep).reshape(-1):
        box = boxes[int(index)] / max(ratio, 1e-9)
        clamped = v5.legacy._clamp_box(tuple(float(value) for value in box), width, height)
        if clamped is None:
            continue
        score = float(scores[int(index)])
        if score >= STRONG_PERSON_SCORE or _partial_person_box_plausible(clamped, width, height):
            result.append((clamped, score))
    return result


def _offset_box(
    box: tuple[int, int, int, int],
    x_offset: int,
    y_offset: int,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int] | None:
    x, y, w, h = box
    return v5.legacy._clamp_box(
        (x + int(x_offset), y + int(y_offset), w, h),
        frame_width,
        frame_height,
    )


def _dedupe_person_proposals(
    values: list[tuple[tuple[int, int, int, int], float, str]],
) -> list[tuple[tuple[int, int, int, int], float, str]]:
    """Remove duplicate full-frame/edge/body-fragment proposals conservatively.

    Standard IoU handles two similarly-sized proposals. A second containment check
    handles the SHOT 0029 failure shape: one substantial strong Person proposal plus
    narrow, weak partial proposals covering only a sleeve/head edge of that same
    person. Coverage is measured against the weak proposal, not the union, so a thin
    contained fragment can be recognized without weakening normal multi-person NMS.
    """

    def covered_by(
        fragment: tuple[int, int, int, int],
        dominant: tuple[int, int, int, int],
    ) -> float:
        fx, fy, fw, fh = fragment
        dx, dy, dw, dh = dominant
        left, top = max(fx, dx), max(fy, dy)
        right, bottom = min(fx + fw, dx + dw), min(fy + fh, dy + dh)
        intersection = max(0, right - left) * max(0, bottom - top)
        return intersection / float(max(1, fw * fh))

    selected: list[tuple[tuple[int, int, int, int], float, str]] = []
    for item in sorted(values, key=lambda value: value[1], reverse=True):
        if any(v5.bbox_iou(item[0], existing[0]) >= EDGE_RETRY_DEDUP_IOU for existing in selected):
            continue
        item_is_weak_partial = bool(
            float(item[1]) < PARTIAL_FRAGMENT_MAX_SCORE
            and "partial" in str(item[2] or "").lower()
        )
        if item_is_weak_partial and any(
            float(existing[1]) >= STRONG_PERSON_SCORE
            and covered_by(item[0], existing[0]) >= PARTIAL_FRAGMENT_STRONG_COVERAGE
            for existing in selected
        ):
            continue
        selected.append(item)
    return selected


def _detect_persons_with_edge_retry(
    detector: _YoloXOrtPersonDetector,
    frame: Any,
) -> list[tuple[tuple[int, int, int, int], float, str]]:
    """先全帧；没有正常 Person 时再放大左右边缘。

    edge retry 命中的框无论分数多高都标记为 partial，因为裁切放大本身不能证明完整 Person 身份；
    它仍必须经过 V6.2 temporal / identity confirmation。
    """

    height, width = frame.shape[:2]
    full = _detect_person_proposals(
        detector,
        frame,
        score_threshold=PARTIAL_PERSON_SCORE,
    )
    values: list[tuple[tuple[int, int, int, int], float, str]] = [
        (
            box,
            score,
            "v6.2-yolox" if score >= STRONG_PERSON_SCORE else "v6.2-yolox-partial",
        )
        for box, score in full
    ]
    if any(score >= STRONG_PERSON_SCORE for _box, score in full):
        return _dedupe_person_proposals(values)

    crop_width = max(32, min(width, int(round(width * EDGE_RETRY_WIDTH_RATIO))))
    if crop_width >= width:
        return _dedupe_person_proposals(values)

    tiles = (
        (0, frame[:, :crop_width]),
        (width - crop_width, frame[:, width - crop_width:]),
    )
    for x_offset, crop in tiles:
        for box, score in _detect_person_proposals(
            detector,
            crop,
            score_threshold=PARTIAL_PERSON_SCORE,
        ):
            mapped = _offset_box(box, x_offset, 0, width, height)
            if mapped is None:
                continue
            if not _partial_person_box_plausible(mapped, width, height):
                continue
            values.append((mapped, score, "v6.2-yolox-edge-partial"))
    return _dedupe_person_proposals(values)


def _source_with_face(proposal_source: str) -> str:
    """Face 不能抹掉 partial provenance；这是 V6.2 防止身份膨胀的关键合同。"""

    source = str(proposal_source or "")
    if "partial" in source.lower():
        return f"{source}+face"
    return "v6.2-yolox+face"


def detect_observations(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[Observation]:
    import cv2

    models = require_models()
    person_detector = _YoloXOrtPersonDetector(models["person_detection.yolox.2022nov"])
    reid = _YoutuReIDOrt(models["person_reid.youtu.2021nov"])
    runtime_label = _runtime_label(person_detector, reid)

    face_detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]),
        "",
        (320, 320),
        score_threshold=v5.legacy.FACE_DETECTION_THRESHOLD,
        nms_threshold=0.30,
        top_k=5000,
    )
    face_recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")

    observations: list[Observation] = []
    total = len(shots)
    for shot_index, shot in enumerate(shots, start=1):
        if progress:
            progress(
                shot_index,
                total,
                f"人物 V6.2 · 12fps Person + Partial Evidence · {runtime_label}：Shot {shot_index} / {total}",
            )
        duration_us = max(1, int(shot["duration_us"]))
        local_times = list(sample_times_us(duration_us))
        for local_us, frame in v5._read_frames(shot["reference_path"], local_times):
            height, width = frame.shape[:2]
            person_entries = _detect_persons_with_edge_retry(person_detector, frame)
            person_boxes = [item[0] for item in person_entries]

            face_detector.setInputSize((width, height))
            _, face_rows = face_detector.detect(frame)
            faces: list[tuple[Any, tuple[int, int, int, int], float]] = []
            if face_rows is not None:
                for row in face_rows:
                    x, y, w, h = [int(round(float(value))) for value in row[:4]]
                    box = v5.legacy._clamp_box((x, y, w, h), width, height)
                    if box is None or box[2] < 18 or box[3] < 18:
                        continue
                    faces.append((row, box, float(row[-1])))

            used_faces: set[int] = set()
            for person_box, person_score, proposal_source in sorted(
                person_entries,
                key=lambda item: item[1],
                reverse=True,
            ):
                other_boxes = [box for box in person_boxes if box != person_box]
                matching: list[tuple[int, Any, tuple[int, int, int, int], float]] = []
                for face_index, (row, face_box, face_score) in enumerate(faces):
                    if face_index in used_faces:
                        continue
                    if v5.legacy._point_inside(v5.legacy._center(face_box), person_box):
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
                    face_embedding=v5.legacy._face_embedding(face_recognizer, frame, face_row) if face_row is not None else None,
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=v5.legacy._body_histogram(frame, person_box),
                    face_visible=face_row is not None,
                    detection_source=_source_with_face(proposal_source) if face_row is not None else proposal_source,
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=v5._clarity_score(frame, person_box),
                    body_completeness=v5._body_completeness(person_box, width, height),
                    interference_ratio=v5._interference_ratio(person_box, other_boxes),
                    other_person_boxes=other_boxes,
                ))

            # 大特写 fallback：YOLOX 没检测到完整 Person，但高置信 Face 明确表示“这里有人”。
            for face_index, (row, face_box, face_score) in enumerate(faces):
                if face_index in used_faces or face_score < v5.legacy.FACE_FALLBACK_THRESHOLD:
                    continue
                person_box = v5.legacy._synthetic_body_box(face_box, width, height)
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
                    face_embedding=v5.legacy._face_embedding(face_recognizer, frame, row),
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=v5.legacy._body_histogram(frame, person_box),
                    face_visible=True,
                    detection_source="v6.2-face-fallback",
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=v5._clarity_score(frame, person_box),
                    body_completeness=v5._body_completeness(person_box, width, height),
                    interference_ratio=v5._interference_ratio(person_box, list(person_boxes)),
                    other_person_boxes=list(person_boxes),
                ))
    return observations
