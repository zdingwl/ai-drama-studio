"""03 资产人物视觉 Evidence V4.1 GPU 执行层。

职责：
- 保持 V4 的 Person → Face → ReID → Track → Candidate 业务算法不变；
- 仅把最重的 YOLOX Person Detection 与 YoutuReID 推理切到 ONNX Runtime；
- 默认 CUDA 优先，失败时自动 CPU fallback；
- YuNet / SFace 继续使用 OpenCV CPU；
- ORT 完全不可用时仍可回退旧 V4 OpenCV CPU 路径，保证项目可运行。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.app import character_visual_v4 as base
from engine.app.inference_runtime_v41 import create_session

CharacterProgress = base.CharacterProgress


class _YoloXOrtPersonDetector:
    """YOLOX ONNX Runtime wrapper；CUDA 优先，CPU 次选。"""

    def __init__(self, model_path: Path):
        import cv2
        import numpy as np

        self.cv2 = cv2
        self.np = np
        self.session, self.runtime = create_session(model_path)
        self.input_name = self.session.get_inputs()[0].name
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
        resized = cv2.resize(
            frame,
            (max(1, int(w * ratio)), max(1, int(h * ratio))),
            interpolation=cv2.INTER_LINEAR,
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        canvas = np.full((self.input_size, self.input_size, 3), 114.0, dtype=np.float32)
        canvas[: rgb.shape[0], : rgb.shape[1]] = rgb
        tensor = np.ascontiguousarray(np.transpose(canvas, (2, 0, 1))[None, :, :, :], dtype=np.float32)
        return tensor, ratio

    def detect(self, frame: Any) -> list[tuple[tuple[int, int, int, int], float]]:
        cv2, np = self.cv2, self.np
        tensor, ratio = self._letterbox(frame)
        outputs = self.session.run(None, {self.input_name: tensor})
        if not outputs:
            return []
        raw = np.asarray(outputs[0])
        dets = raw[0].copy() if raw.ndim == 3 else raw.copy()
        if dets.ndim != 2 or dets.shape[0] != self.grids.shape[0] or dets.shape[1] < 6:
            return []
        dets[:, :2] = (dets[:, :2] + self.grids) * self.expanded_strides
        dets[:, 2:4] = np.exp(dets[:, 2:4]) * self.expanded_strides
        person_scores = dets[:, 4] * dets[:, 5]
        mask = person_scores >= base.PERSON_SCORE_THRESHOLD
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
            base.PERSON_SCORE_THRESHOLD,
            base.PERSON_NMS_THRESHOLD,
        )
        if len(keep) == 0:
            return []
        height, width = frame.shape[:2]
        result: list[tuple[tuple[int, int, int, int], float]] = []
        for index in np.asarray(keep).reshape(-1):
            box = boxes[int(index)] / max(ratio, 1e-9)
            clamped = base._clamp_box(tuple(float(value) for value in box), width, height)
            if clamped is not None:
                result.append((clamped, float(scores[int(index)])))
        return result


class _YoutuReIDOrt:
    """YoutuReID ONNX Runtime wrapper；CUDA 优先，CPU 次选。"""

    def __init__(self, model_path: Path):
        import cv2

        self.cv2 = cv2
        self.session, self.runtime = create_session(model_path)
        self.input_name = self.session.get_inputs()[0].name

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
        tensor = np.ascontiguousarray(np.transpose(image, (2, 0, 1))[None, :, :, :], dtype=np.float32)
        outputs = self.session.run(None, {self.input_name: tensor})
        if not outputs:
            return None
        feature = np.asarray(outputs[0]).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feature))
        return feature / norm if norm > 1e-9 else None


def _runtime_label(person: _YoloXOrtPersonDetector, reid: _YoutuReIDOrt) -> str:
    person_device = str(person.runtime.get("device") or "CPU")
    reid_device = str(reid.runtime.get("device") or "CPU")
    if person_device == "GPU" and reid_device == "GPU":
        return "GPU · CUDA"
    if person_device == "GPU" or reid_device == "GPU":
        return f"混合 · Person {person_device} / ReID {reid_device}"
    return "CPU fallback"


def detect_observations(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[base.Observation]:
    """V4.1 Person Observation：重模型 GPU 优先；Face/SFace 保持 CPU。"""

    import cv2

    models = base.require_models()
    try:
        person_detector = _YoloXOrtPersonDetector(models["person_detection.yolox.2022nov"])
        reid = _YoutuReIDOrt(models["person_reid.youtu.2021nov"])
    except (ImportError, ModuleNotFoundError):
        # 兼容旧环境：requirements 尚未更新完成时仍可走 V4 OpenCV CPU。
        if progress:
            progress(0, max(1, len(shots)), "人物识别：ONNX Runtime 未安装，使用 CPU fallback")
        return base.detect_observations(shots, progress=progress)

    runtime_label = _runtime_label(person_detector, reid)
    face_detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]),
        "",
        (320, 320),
        score_threshold=base.FACE_DETECTION_THRESHOLD,
        nms_threshold=0.30,
        top_k=5000,
    )
    face_recognizer = cv2.FaceRecognizerSF.create(
        str(models["face_recognition.sface.2021dec"]), ""
    )

    observations: list[base.Observation] = []
    total = len(shots)
    for shot_index, shot in enumerate(shots, start=1):
        if progress:
            progress(
                shot_index,
                total,
                f"人物识别 · {runtime_label}：Shot {shot_index} / {total}",
            )
        duration_us = max(1, int(shot["duration_us"]))
        local_times = sorted({
            max(0, min(duration_us - 1, int(duration_us * ratio)))
            for ratio in base.sample_ratios(duration_us)
        })
        for local_us, frame in base._read_frames(shot["reference_path"], local_times):
            height, width = frame.shape[:2]
            persons = person_detector.detect(frame)

            face_detector.setInputSize((width, height))
            _, face_rows = face_detector.detect(frame)
            faces: list[tuple[Any, tuple[int, int, int, int], float]] = []
            if face_rows is not None:
                for row in face_rows:
                    x, y, w, h = [int(round(float(value))) for value in row[:4]]
                    box = base._clamp_box((x, y, w, h), width, height)
                    if box is None or box[2] < 18 or box[3] < 18:
                        continue
                    faces.append((row, box, float(row[-1])))

            used_faces: set[int] = set()
            for person_box, person_score in sorted(persons, key=lambda item: item[1], reverse=True):
                matching: list[tuple[int, Any, tuple[int, int, int, int], float]] = []
                for face_index, (row, face_box, face_score) in enumerate(faces):
                    if face_index in used_faces:
                        continue
                    if base._point_inside(base._center(face_box), person_box):
                        matching.append((face_index, row, face_box, face_score))
                face_row = None
                face_box = None
                face_score = 0.0
                if matching:
                    face_index, face_row, face_box, face_score = max(matching, key=lambda item: item[3])
                    used_faces.add(face_index)
                observations.append(base.Observation(
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
                    face_embedding=base._face_embedding(face_recognizer, frame, face_row) if face_row is not None else None,
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=base._body_histogram(frame, person_box),
                    face_visible=face_row is not None,
                    detection_source="yolox-ort+face" if face_row is not None else "yolox-ort",
                ))

            for face_index, (row, face_box, face_score) in enumerate(faces):
                if face_index in used_faces or face_score < base.FACE_FALLBACK_THRESHOLD:
                    continue
                person_box = base._synthetic_body_box(face_box, width, height)
                observations.append(base.Observation(
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
                    face_embedding=base._face_embedding(face_recognizer, frame, row),
                    reid_embedding=reid.infer(frame, person_box),
                    body_hist=base._body_histogram(frame, person_box),
                    face_visible=True,
                    detection_source="face_fallback+reid-ort",
                ))
    return observations


def analyze_characters(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[base.CandidateDraft]:
    """人物 V4.1 总入口：GPU-first Observation → 原 V4 Track / Identity Clustering。"""

    observations = detect_observations(shots, progress=progress)
    return base.cluster_candidates(base.build_tracks(observations))
