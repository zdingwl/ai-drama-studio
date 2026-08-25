"""Character V6 Person Observation。

职责：
- 复用已校验的 YOLOX Person / YoutuReID / YuNet / SFace 模型；
- 把 Shot 内人物检测采样从 V5 的约 6fps 提升到约 12fps，为成熟 MOT 提供连续轨迹；
- 每个采样帧先数清 Person，再把 Face / ReID / 清晰度 / 多人干扰作为 Observation Evidence；
- 大特写 Person Detector 失败时仍保留高置信 Face fallback。

这里只负责“这个时刻画面里有谁的视觉观测”，不做 Track，不创建 Character_ID。
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
                f"人物 V6 · 12fps Person Evidence · {runtime_label}：Shot {shot_index} / {total}",
            )
        duration_us = max(1, int(shot["duration_us"]))
        local_times = list(sample_times_us(duration_us))
        for local_us, frame in v5._read_frames(shot["reference_path"], local_times):
            height, width = frame.shape[:2]
            persons = person_detector.detect(frame)
            person_boxes = [item[0] for item in persons]

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
            for person_box, person_score in sorted(persons, key=lambda item: item[1], reverse=True):
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
                    detection_source="v6-yolox+face" if face_row is not None else "v6-yolox",
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
                    detection_source="v6-face-fallback",
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=v5._clarity_score(frame, person_box),
                    body_completeness=v5._body_completeness(person_box, width, height),
                    interference_ratio=v5._interference_ratio(person_box, list(person_boxes)),
                    other_person_boxes=list(person_boxes),
                ))
    return observations
