"""Character V6.3 Person Observation：在 V6.2 recall 基础上增加安全 Face ownership。

核心约束：
- 继续复用 V6.2 的 12fps、partial-person、edge retry；不降低召回。
- partial proposal 永远不抢 Face。局部人体只提供 body/ReID Evidence。
- 正常 Person 与 Face 使用全局一对一匹配，而不是“Face 中心落进谁的框就归谁”。
- Face 必须大部分被 Person bbox 包含，并位于人体上部、水平位置合理。
- 没有安全归属的高置信 Face 继续走独立 face fallback，避免漏掉大特写。

为什么：多人近景中一个较大的 Person bbox 可能同时包住旁边人的脸。旧的 inside-center 规则会把
“甲的身体 + 乙的脸”组成一个污染 Track，后面的 Global Identity 再严格也无法恢复。
"""
from __future__ import annotations

from typing import Any

from engine.app import character_observation_v6 as v62
from engine.app import character_visual_v5 as v5
from engine.app.character_visual_gpu_v41 import _YoloXOrtPersonDetector, _YoutuReIDOrt, _runtime_label
from engine.app.content_models_v2 import require_models

CharacterProgress = v5.CharacterProgress
Observation = v5.Observation
sample_times_us = v62.sample_times_us

FACE_OWNER_MIN_COVERAGE = 0.78
FACE_OWNER_MAX_VERTICAL_CENTER = 0.58
FACE_OWNER_MAX_WIDTH_RATIO = 0.78
FACE_OWNER_MAX_HEIGHT_RATIO = 0.58


def _intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    return max(0, right - left) * max(0, bottom - top)


def _face_owner_score(
    person_box: tuple[int, int, int, int],
    face_box: tuple[int, int, int, int],
    face_score: float,
    proposal_source: str,
) -> float | None:
    """返回 Face 属于 Person 的几何可信度；不可信返回 None。

    partial proposal 不参与 Face ownership。它们若真的包含可见脸，未被占用的 Face 会走 face fallback，
    从而避免 partial 大框把旁边人的 Face 抢走。
    """

    if "partial" in str(proposal_source or "").lower():
        return None

    px, py, pw, ph = person_box
    fx, fy, fw, fh = face_box
    if pw <= 0 or ph <= 0 or fw <= 0 or fh <= 0:
        return None

    face_area = max(1, fw * fh)
    coverage = _intersection_area(person_box, face_box) / float(face_area)
    if coverage < FACE_OWNER_MIN_COVERAGE:
        return None

    face_cx = fx + fw * 0.5
    face_cy = fy + fh * 0.5
    nx = (face_cx - px) / float(pw)
    ny = (face_cy - py) / float(ph)
    if nx < -0.05 or nx > 1.05 or ny < -0.08 or ny > FACE_OWNER_MAX_VERTICAL_CENTER:
        return None

    width_ratio = fw / float(pw)
    height_ratio = fh / float(ph)
    if width_ratio > FACE_OWNER_MAX_WIDTH_RATIO or height_ratio > FACE_OWNER_MAX_HEIGHT_RATIO:
        return None

    horizontal = max(0.0, 1.0 - abs(nx - 0.5) / 0.55)
    upper_body = max(0.0, 1.0 - max(0.0, ny) / FACE_OWNER_MAX_VERTICAL_CENTER)
    return (
        max(0.0, min(1.0, float(face_score))) * 0.46
        + coverage * 0.28
        + horizontal * 0.14
        + upper_body * 0.12
    )


def _assign_faces_to_persons(
    person_entries: list[tuple[tuple[int, int, int, int], float, str]],
    faces: list[tuple[Any, tuple[int, int, int, int], float]],
) -> tuple[dict[int, int], set[int]]:
    """全局一对一 Face→Person 匹配。

    先构造所有几何合法 pair，再按 ownership score 从高到低贪心选取；一个 Face/Person 只能使用一次。
    """

    pairs: list[tuple[float, int, int]] = []
    for person_index, (person_box, _person_score, proposal_source) in enumerate(person_entries):
        for face_index, (_row, face_box, face_score) in enumerate(faces):
            score = _face_owner_score(person_box, face_box, face_score, proposal_source)
            if score is not None:
                pairs.append((score, person_index, face_index))

    assigned: dict[int, int] = {}
    used_faces: set[int] = set()
    for _score, person_index, face_index in sorted(pairs, reverse=True):
        if person_index in assigned or face_index in used_faces:
            continue
        assigned[person_index] = face_index
        used_faces.add(face_index)
    return assigned, used_faces


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
                f"人物 V6.3 · Safe Face Ownership + Partial Evidence · {runtime_label}：Shot {shot_index} / {total}",
            )

        duration_us = max(1, int(shot["duration_us"]))
        local_times = list(sample_times_us(duration_us))
        for local_us, frame in v5._read_frames(shot["reference_path"], local_times):
            height, width = frame.shape[:2]
            person_entries = v62._detect_persons_with_edge_retry(person_detector, frame)
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

            face_assignment, used_faces = _assign_faces_to_persons(person_entries, faces)

            for person_index, (person_box, person_score, proposal_source) in enumerate(person_entries):
                other_boxes = [box for index, box in enumerate(person_boxes) if index != person_index]
                face_row = None
                face_box = None
                face_score = 0.0
                face_index = face_assignment.get(person_index)
                if face_index is not None:
                    face_row, face_box, face_score = faces[face_index]

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
                    detection_source="v6.3-yolox+face" if face_row is not None else proposal_source.replace("v6.2", "v6.3"),
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=v5._clarity_score(frame, person_box),
                    body_completeness=v5._body_completeness(person_box, width, height),
                    interference_ratio=v5._interference_ratio(person_box, other_boxes),
                    other_person_boxes=other_boxes,
                ))

            # 未安全归属给 Person 的高置信 Face 仍保留为独立 Face fallback。
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
                    detection_source="v6.3-face-fallback",
                    frame_width=width,
                    frame_height=height,
                    face_score=face_score,
                    clarity_score=v5._clarity_score(frame, person_box),
                    body_completeness=v5._body_completeness(person_box, width, height),
                    interference_ratio=v5._interference_ratio(person_box, list(person_boxes)),
                    other_person_boxes=list(person_boxes),
                ))
    return observations
