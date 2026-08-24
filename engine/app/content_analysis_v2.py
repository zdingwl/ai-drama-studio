"""F05「智能内容识别」V2。

目标不是把原镜头重新写成冗长文字，而是围绕 Reference Clip 提取重制阶段必须控制的语义：
人物身份/Track、Scene、关键道具入口、源对白、Speaker 以及轻量镜头说明。

当前本地基线：
- 人物：YuNet + SFace，并把人物身体/服装区域颜色特征作为辅助证据；
- Scene：缩略图 HSV 视觉聚类；
- ASR：可选 faster-whisper；
- Speaker：可选本地 pyannote Pipeline，未配置时明确返回 NOT_CONFIGURED；
- Key Prop：表结构与状态已建立，V1 不在没有对象模型时伪造识别结果。

F05 保存的是 AI Evidence。F06 才产生人工 Final Character / Scene / Prop / Dialogue。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import math
import os
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.content_models_v2 import ContentModelError, model_status, require_models
from engine.app.studio_v2 import Base, Episode, Project, Shot, get_session, new_id, utcnow, workspace_root

PROFILE_VERSION = "f05-v2.1"
SAMPLE_RATIOS = (0.18, 0.50, 0.82)
FACE_CLUSTER_THRESHOLD = 0.45
TRACK_FACE_THRESHOLD = 0.38
TRACK_BODY_THRESHOLD = 0.90
BODY_ONLY_CLUSTER_THRESHOLD = 0.975
SCENE_CLUSTER_THRESHOLD = 0.72


class ContentAnalysisError(RuntimeError):
    """F05 对 Controller 暴露的业务错误。"""


class ContentAnalysisRun(Base):
    __tablename__ = "v2_content_analysis_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROCESSING")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    profile_version: Mapped[str] = mapped_column(String(32), nullable=False, default=PROFILE_VERSION)
    component_status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    counts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CharacterCandidate(Base):
    __tablename__ = "v2_character_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_label: Mapped[str] = mapped_column(String(100), nullable=False)
    track_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cover_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class CharacterTrack(Base):
    __tablename__ = "v2_character_tracks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("v2_character_candidates.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    representative_source_us: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_json: Mapped[str] = mapped_column(Text, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    face_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mean_face_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_evidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class SceneCandidate(Base):
    __tablename__ = "v2_scene_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_label: Mapped[str] = mapped_column(String(100), nullable=False)
    shot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cover_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class ShotSceneEvidence(Base):
    __tablename__ = "v2_shot_scene_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    scene_candidate_id: Mapped[str] = mapped_column(ForeignKey("v2_scene_candidates.id", ondelete="CASCADE"), index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class PropCandidate(Base):
    __tablename__ = "v2_prop_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_label: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class ShotPropEvidence(Base):
    __tablename__ = "v2_shot_prop_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    prop_candidate_id: Mapped[str] = mapped_column(ForeignKey("v2_prop_candidates.id", ondelete="CASCADE"), index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SpeakerSegment(Base):
    __tablename__ = "v2_speaker_segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class AnalysisDialogue(Base):
    __tablename__ = "v2_analysis_dialogues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_content_analysis_runs.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    source_start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    shot_start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    shot_end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    speaker_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    speaker_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("v2_character_candidates.id", ondelete="SET NULL"), nullable=True)
    speaker_mapping_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    dialogue_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speaking_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


@dataclass
class Observation:
    shot_id: str
    episode_id: str
    episode_order: int
    shot_ordinal: int
    source_time_us: int
    local_time_us: int
    bbox: tuple[int, int, int, int]
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


@dataclass
class SceneDraft:
    id: str
    shot_ids: list[str] = field(default_factory=list)
    centroid: Any | None = None
    cover_path: str | None = None
    scores: list[float] = field(default_factory=list)


def _cosine(left: Any | None, right: Any | None) -> float | None:
    if left is None or right is None:
        return None
    import numpy as np

    a = np.asarray(left, dtype=np.float32).reshape(-1)
    b = np.asarray(right, dtype=np.float32).reshape(-1)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 1e-9:
        return None
    return float(np.dot(a, b) / denominator)


def _mean_vector(values: list[Any]) -> Any | None:
    if not values:
        return None
    import numpy as np

    array = np.stack([np.asarray(value, dtype=np.float32).reshape(-1) for value in values])
    mean = array.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    return mean / norm if norm > 1e-9 else mean


def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def _body_histogram(frame: Any, face_bbox: tuple[int, int, int, int]) -> Any | None:
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    x, y, w, h = face_bbox
    left = max(0, int(x - 0.65 * w))
    right = min(width, int(x + 1.65 * w))
    top = max(0, int(y + 0.65 * h))
    bottom = min(height, int(y + 4.6 * h))
    if right - left < 16 or bottom - top < 24:
        return None
    crop = frame[top:bottom, left:right]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 12], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(hist))
    return hist / norm if norm > 1e-9 else None


def _read_frame(reference_path: str, local_time_us: int) -> Any | None:
    import cv2

    capture = cv2.VideoCapture(reference_path)
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, local_time_us / 1000.0)
        ok, frame = capture.read()
        return frame if ok else None
    finally:
        capture.release()


def _detect_character_observations(shots: list[dict[str, Any]]) -> list[Observation]:
    import cv2
    import numpy as np

    models = require_models()
    detector = cv2.FaceDetectorYN.create(
        str(models["face_detection.yunet.2023mar"]), "", (320, 320),
        score_threshold=0.90, nms_threshold=0.30, top_k=5000,
    )
    recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")
    observations: list[Observation] = []

    for shot in shots:
        duration_us = int(shot["duration_us"])
        for ratio in SAMPLE_RATIOS:
            local_us = max(0, min(duration_us - 1, int(duration_us * ratio)))
            frame = _read_frame(shot["reference_path"], local_us)
            if frame is None:
                continue
            height, width = frame.shape[:2]
            detector.setInputSize((width, height))
            _, faces = detector.detect(frame)
            if faces is None:
                continue
            for row in faces:
                x, y, w, h = [int(round(float(value))) for value in row[:4]]
                score = float(row[-1])
                if w < 28 or h < 28:
                    continue
                x = max(0, x)
                y = max(0, y)
                w = min(width - x, w)
                h = min(height - y, h)
                if w <= 0 or h <= 0:
                    continue
                try:
                    aligned = recognizer.alignCrop(frame, row)
                    feature = recognizer.feature(aligned).reshape(-1).astype(np.float32)
                    norm = float(np.linalg.norm(feature))
                    embedding = feature / norm if norm > 1e-9 else None
                except Exception:
                    embedding = None
                observations.append(Observation(
                    shot_id=shot["id"], episode_id=shot["episode_id"],
                    episode_order=shot["episode_order"], shot_ordinal=shot["ordinal"],
                    source_time_us=shot["start_us"] + local_us, local_time_us=local_us,
                    bbox=(x, y, w, h), reference_path=shot["reference_path"],
                    detection_score=score, face_embedding=embedding,
                    body_hist=_body_histogram(frame, (x, y, w, h)), face_visible=True,
                ))
    return observations


def _build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    by_shot: dict[str, list[Observation]] = {}
    for item in observations:
        by_shot.setdefault(item.shot_id, []).append(item)

    result: list[TrackDraft] = []
    for shot_observations in by_shot.values():
        tracks: list[TrackDraft] = []
        for observation in sorted(shot_observations, key=lambda item: item.source_time_us):
            best: TrackDraft | None = None
            best_score = -1.0
            for track in tracks:
                last = track.observations[-1]
                if observation.source_time_us == last.source_time_us:
                    continue
                face_score = _cosine(track.face_embedding, observation.face_embedding)
                body_score = _cosine(track.body_hist, observation.body_hist)
                spatial = _bbox_iou(last.bbox, observation.bbox)
                qualifies = (face_score is not None and face_score >= TRACK_FACE_THRESHOLD) or (
                    body_score is not None and body_score >= TRACK_BODY_THRESHOLD and spatial >= 0.01
                )
                if not qualifies:
                    continue
                score = (face_score or 0.0) * 0.82 + (body_score or 0.0) * 0.13 + spatial * 0.05
                if score > best_score:
                    best, best_score = track, score
            if best is None:
                best = TrackDraft(
                    shot_id=observation.shot_id, episode_id=observation.episode_id,
                    episode_order=observation.episode_order, shot_ordinal=observation.shot_ordinal,
                )
                tracks.append(best)
            best.observations.append(observation)
            best.face_embedding = _mean_vector([item.face_embedding for item in best.observations if item.face_embedding is not None])
            best.body_hist = _mean_vector([item.body_hist for item in best.observations if item.body_hist is not None])
        result.extend(tracks)
    return result


def _cluster_characters(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    candidates: list[CandidateDraft] = []
    ordered = sorted(tracks, key=lambda item: (item.episode_order, item.shot_ordinal))
    for track in ordered:
        best: CandidateDraft | None = None
        best_score = -1.0
        for candidate in candidates:
            if any(member.shot_id == track.shot_id for member in candidate.tracks):
                continue
            face_score = _cosine(candidate.face_embedding, track.face_embedding)
            body_score = _cosine(candidate.body_hist, track.body_hist)
            if face_score is not None:
                qualifies = face_score >= FACE_CLUSTER_THRESHOLD
                score = face_score * 0.88 + (body_score or 0.0) * 0.12
            else:
                previous = candidate.tracks[-1]
                adjacent = previous.episode_id == track.episode_id and abs(previous.shot_ordinal - track.shot_ordinal) <= 1
                qualifies = adjacent and body_score is not None and body_score >= BODY_ONLY_CLUSTER_THRESHOLD
                score = body_score or 0.0
            if qualifies and score > best_score:
                best, best_score = candidate, score
        if best is None:
            best = CandidateDraft(id=new_id("CHAR_CANDIDATE"))
            candidates.append(best)
        else:
            best.scores.append(best_score)
        best.tracks.append(track)
        best.face_embedding = _mean_vector([member.face_embedding for member in best.tracks if member.face_embedding is not None])
        best.body_hist = _mean_vector([member.body_hist for member in best.tracks if member.body_hist is not None])
    return candidates


def _save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    import cv2

    observations = [item for track in candidate.tracks for item in track.observations]
    if not observations:
        return None
    representative = max(observations, key=lambda item: item.detection_score)
    frame = _read_frame(representative.reference_path, representative.local_time_us)
    if frame is None:
        return None
    x, y, w, h = representative.bbox
    height, width = frame.shape[:2]
    pad_x, pad_y = int(w * 0.45), int(h * 0.45)
    left, top = max(0, x - pad_x), max(0, y - pad_y)
    right, bottom = min(width, x + w + pad_x), min(height, y + h + int(h * 1.6))
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    path = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path) if cv2.imwrite(str(path), crop) else None


def _scene_descriptor(path: str | None) -> Any | None:
    if not path:
        return None
    import cv2
    import numpy as np

    image = cv2.imread(path)
    if image is None:
        return None
    image = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 12], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(hist))
    return hist / norm if norm > 1e-9 else None


def _cluster_scenes(run_id: str, project_id: str, shots: list[dict[str, Any]]) -> list[SceneDraft]:
    scenes: list[SceneDraft] = []
    for shot in shots:
        descriptor = _scene_descriptor(shot.get("thumbnail_path"))
        if descriptor is None:
            continue
        best: SceneDraft | None = None
        best_score = -1.0
        for scene in scenes:
            score = _cosine(scene.centroid, descriptor) or -1.0
            if score >= SCENE_CLUSTER_THRESHOLD and score > best_score:
                best, best_score = scene, score
        if best is None:
            best = SceneDraft(id=new_id("SCENE_CANDIDATE"), cover_path=shot.get("thumbnail_path"))
            scenes.append(best)
        else:
            best.scores.append(best_score)
        best.shot_ids.append(shot["id"])
        descriptors = [_scene_descriptor(next(item.get("thumbnail_path") for item in shots if item["id"] == sid)) for sid in best.shot_ids]
        best.centroid = _mean_vector([value for value in descriptors if value is not None])
    return scenes


def _language_code(locale: str) -> str | None:
    value = (locale or "").strip().lower()
    mapping = {
        "zh-cn": "zh", "zh-tw": "zh", "en-us": "en", "en-gb": "en",
        "ja-jp": "ja", "ko-kr": "ko", "es-es": "es", "pt-br": "pt",
    }
    return mapping.get(value, value.split("-", 1)[0] if value else None)


def _run_asr(project: dict[str, Any], episodes: list[dict[str, Any]], shots: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return "NOT_AVAILABLE", []

    model_name = os.getenv("AI_DRAMA_WHISPER_MODEL", "small")
    requested_device = os.getenv("AI_DRAMA_WHISPER_DEVICE", "auto").lower()
    if requested_device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    else:
        device = requested_device
    compute_type = os.getenv("AI_DRAMA_WHISPER_COMPUTE_TYPE", "float16" if device == "cuda" else "int8")
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception:
        if device == "cuda":
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
        else:
            raise

    shots_by_episode: dict[str, list[dict[str, Any]]] = {}
    for shot in shots:
        shots_by_episode.setdefault(shot["episode_id"], []).append(shot)

    results: list[dict[str, Any]] = []
    for episode in episodes:
        audio_path = episode.get("audio_path")
        if not audio_path or not Path(audio_path).is_file():
            continue
        segments, info = model.transcribe(
            audio_path,
            language=_language_code(project["source_language"]),
            beam_size=5,
            vad_filter=True,
            word_timestamps=False,
        )
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            start_us = max(0, int(round(float(segment.start) * 1_000_000)))
            end_us = max(start_us + 1, int(round(float(segment.end) * 1_000_000)))
            candidates = shots_by_episode.get(episode["id"], [])
            best_shot = None
            best_overlap = 0
            for shot in candidates:
                overlap = max(0, min(end_us, shot["end_us"]) - max(start_us, shot["start_us"]))
                if overlap > best_overlap:
                    best_overlap, best_shot = overlap, shot
            if best_shot is None:
                continue
            results.append({
                "id": new_id("AI_DIALOGUE"), "episode_id": episode["id"], "shot_id": best_shot["id"],
                "source_start_us": start_us, "source_end_us": end_us,
                "shot_start_us": max(0, start_us - best_shot["start_us"]),
                "shot_end_us": min(best_shot["duration_us"], max(1, end_us - best_shot["start_us"])),
                "ai_text": text, "language": getattr(info, "language", None),
                "speaker_label": None, "speaker_candidate_id": None, "speaker_mapping_confidence": None,
                "dialogue_type": "unknown", "emotion": None, "speaking_style": None,
                "confidence": None,
                "evidence": {"provider": "faster-whisper", "model": model_name, "device": device},
            })
    return "READY" if results else "NO_DIALOGUE", results


def _run_diarization(episodes: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    model_path = os.getenv("AI_DRAMA_DIARIZATION_MODEL_PATH", "").strip()
    if not model_path:
        return "NOT_CONFIGURED", []
    if not Path(model_path).exists():
        return "MODEL_MISSING", []
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        return "NOT_AVAILABLE", []

    pipeline = Pipeline.from_pretrained(model_path)
    try:
        import torch
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
    except Exception:
        pass

    output: list[dict[str, Any]] = []
    for episode in episodes:
        audio_path = episode.get("audio_path")
        if not audio_path or not Path(audio_path).is_file():
            continue
        result = pipeline(audio_path)
        diarization = getattr(result, "exclusive_speaker_diarization", None) or getattr(result, "speaker_diarization", result)
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            output.append({
                "id": new_id("SPEAKER_SEGMENT"), "episode_id": episode["id"],
                "start_us": int(round(float(turn.start) * 1_000_000)),
                "end_us": int(round(float(turn.end) * 1_000_000)),
                "speaker_label": str(speaker), "confidence": None,
            })
    return "READY" if output else "NO_SPEECH", output


def _attach_speakers(dialogues: list[dict[str, Any]], speaker_segments: list[dict[str, Any]]) -> None:
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for item in speaker_segments:
        by_episode.setdefault(item["episode_id"], []).append(item)
    for dialogue in dialogues:
        best = None
        best_overlap = 0
        for segment in by_episode.get(dialogue["episode_id"], []):
            overlap = max(0, min(dialogue["source_end_us"], segment["end_us"]) - max(dialogue["source_start_us"], segment["start_us"]))
            if overlap > best_overlap:
                best, best_overlap = segment, overlap
        if best is not None:
            dialogue["speaker_label"] = best["speaker_label"]


def _map_speaker_to_character(dialogues: list[dict[str, Any]], candidates: list[CandidateDraft]) -> None:
    candidates_by_shot: dict[str, set[str]] = {}
    for candidate in candidates:
        for track in candidate.tracks:
            candidates_by_shot.setdefault(track.shot_id, set()).add(candidate.id)

    scores: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for dialogue in dialogues:
        speaker = dialogue.get("speaker_label")
        if not speaker:
            continue
        totals[speaker] = totals.get(speaker, 0) + 1
        visible = candidates_by_shot.get(dialogue["shot_id"], set())
        for candidate_id in visible:
            scores.setdefault(speaker, {})[candidate_id] = scores.setdefault(speaker, {}).get(candidate_id, 0) + 1

    mapping: dict[str, tuple[str, float]] = {}
    for speaker, candidate_scores in scores.items():
        if not candidate_scores:
            continue
        ordered = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
        candidate_id, count = ordered[0]
        second = ordered[1][1] if len(ordered) > 1 else 0
        total = max(1, totals.get(speaker, 1))
        confidence = count / total
        if count >= 2 and confidence >= 0.60 and count > second:
            mapping[speaker] = (candidate_id, min(0.90, confidence))

    for dialogue in dialogues:
        speaker = dialogue.get("speaker_label")
        if speaker in mapping:
            dialogue["speaker_candidate_id"], dialogue["speaker_mapping_confidence"] = mapping[speaker]
            dialogue["dialogue_type"] = "dialogue"
        elif speaker:
            visible = candidates_by_shot.get(dialogue["shot_id"], set())
            if len(visible) == 1:
                dialogue["speaker_candidate_id"] = next(iter(visible))
                dialogue["speaker_mapping_confidence"] = 0.50
                dialogue["dialogue_type"] = "dialogue"


def _load_context(project_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        episodes = session.scalars(select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order)).all()
        if not episodes:
            raise ContentAnalysisError("项目还没有剧集")
        episode_payloads: list[dict[str, Any]] = []
        shots: list[dict[str, Any]] = []
        for episode in episodes:
            preprocess = episode.preprocess
            episode_shots = session.scalars(select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.ordinal)).all()
            if not episode_shots:
                raise ContentAnalysisError(f"第 {episode.sort_order} 集还没有完成 F04 自动拉片")
            episode_payloads.append({
                "id": episode.id, "sort_order": episode.sort_order,
                "audio_path": preprocess.audio_path if preprocess else None,
            })
            for shot in episode_shots:
                shots.append({
                    "id": shot.id, "episode_id": episode.id, "episode_order": episode.sort_order,
                    "ordinal": shot.ordinal, "start_us": shot.start_us, "end_us": shot.end_us,
                    "duration_us": shot.duration_us, "reference_path": shot.reference_clip_path,
                    "thumbnail_path": shot.thumbnail_path,
                })
        return ({
            "id": project.id, "source_language": project.source_language,
            "target_language": project.target_language, "target_region": project.target_region,
        }, episode_payloads, shots)


def _create_run(project_id: str) -> str:
    run_id = new_id("CONTENT_RUN")
    with get_session() as session:
        session.add(ContentAnalysisRun(
            id=run_id, project_id=project_id, status="PROCESSING", is_current=False,
            profile_version=PROFILE_VERSION, component_status_json="{}", counts_json="{}",
        ))
        session.commit()
    return run_id


def _fail_run(run_id: str, message: str) -> None:
    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run:
            run.status = "FAILED"
            run.error_message = message
            run.completed_at = utcnow()
            session.commit()


def _persist_results(
    *, run_id: str, project_id: str, shots: list[dict[str, Any]], candidates: list[CandidateDraft],
    scenes: list[SceneDraft], dialogues: list[dict[str, Any]], speaker_segments: list[dict[str, Any]],
    component_status: dict[str, str],
) -> None:
    scene_by_shot: dict[str, str] = {}
    with get_session() as session:
        for ordinal, candidate in enumerate(candidates, start=1):
            cover_path = _save_candidate_cover(run_id, candidate, ordinal)
            confidence = sum(candidate.scores) / len(candidate.scores) if candidate.scores else None
            session.add(CharacterCandidate(
                id=candidate.id, run_id=run_id, project_id=project_id, ordinal=ordinal,
                auto_label=f"人物 {ordinal:03d}", track_count=len(candidate.tracks),
                shot_count=len({item.shot_id for item in candidate.tracks}), confidence=confidence,
                cover_path=cover_path,
                evidence_json=json.dumps({"identity": "SFace + body color evidence", "profile": PROFILE_VERSION}, ensure_ascii=False),
            ))
            for track in candidate.tracks:
                representative = max(track.observations, key=lambda item: item.detection_score)
                face_scores = [item.detection_score for item in track.observations if item.face_visible]
                body_scores = [_cosine(track.body_hist, item.body_hist) for item in track.observations if item.body_hist is not None]
                session.add(CharacterTrack(
                    id=new_id("CHAR_TRACK"), run_id=run_id, candidate_id=candidate.id, shot_id=track.shot_id,
                    start_us=min(item.source_time_us for item in track.observations),
                    end_us=max(item.source_time_us for item in track.observations) + 1,
                    representative_source_us=representative.source_time_us,
                    bbox_json=json.dumps(list(representative.bbox)), sample_count=len(track.observations),
                    face_visible=any(item.face_visible for item in track.observations),
                    mean_face_score=sum(face_scores) / len(face_scores) if face_scores else None,
                    body_evidence_score=(sum(value for value in body_scores if value is not None) / len([value for value in body_scores if value is not None])) if any(value is not None for value in body_scores) else None,
                    evidence_json=json.dumps({
                        "samples": [
                            {"source_time_us": item.source_time_us, "bbox": list(item.bbox), "score": item.detection_score}
                            for item in track.observations
                        ]
                    }, ensure_ascii=False),
                ))

        for ordinal, scene in enumerate(scenes, start=1):
            session.add(SceneCandidate(
                id=scene.id, run_id=run_id, project_id=project_id, ordinal=ordinal,
                auto_label=f"场景 {ordinal:03d}", shot_count=len(scene.shot_ids), cover_path=scene.cover_path,
                evidence_json=json.dumps({"method": "HSV visual clustering", "profile": PROFILE_VERSION}, ensure_ascii=False),
            ))
            for shot_id in scene.shot_ids:
                scene_by_shot[shot_id] = scene.id
                session.add(ShotSceneEvidence(
                    id=new_id("SHOT_SCENE"), run_id=run_id, shot_id=shot_id,
                    scene_candidate_id=scene.id,
                    confidence=(sum(scene.scores) / len(scene.scores)) if scene.scores else 1.0,
                ))

        for item in speaker_segments:
            session.add(SpeakerSegment(
                id=item["id"], run_id=run_id, episode_id=item["episode_id"],
                start_us=item["start_us"], end_us=item["end_us"], speaker_label=item["speaker_label"],
                confidence=item.get("confidence"),
            ))
        for item in dialogues:
            session.add(AnalysisDialogue(
                id=item["id"], run_id=run_id, episode_id=item["episode_id"], shot_id=item["shot_id"],
                source_start_us=item["source_start_us"], source_end_us=item["source_end_us"],
                shot_start_us=item["shot_start_us"], shot_end_us=item["shot_end_us"], ai_text=item["ai_text"],
                language=item.get("language"), speaker_label=item.get("speaker_label"),
                speaker_candidate_id=item.get("speaker_candidate_id"),
                speaker_mapping_confidence=item.get("speaker_mapping_confidence"),
                dialogue_type=item.get("dialogue_type") or "unknown", emotion=item.get("emotion"),
                speaking_style=item.get("speaking_style"), confidence=item.get("confidence"),
                evidence_json=json.dumps(item.get("evidence") or {}, ensure_ascii=False),
            ))

        character_count_by_shot: dict[str, int] = {}
        for candidate in candidates:
            for shot_id in {track.shot_id for track in candidate.tracks}:
                character_count_by_shot[shot_id] = character_count_by_shot.get(shot_id, 0) + 1
        dialogue_count_by_shot: dict[str, int] = {}
        for dialogue in dialogues:
            dialogue_count_by_shot[dialogue["shot_id"]] = dialogue_count_by_shot.get(dialogue["shot_id"], 0) + 1
        for shot_payload in shots:
            shot = session.get(Shot, shot_payload["id"])
            if shot is None:
                continue
            parts: list[str] = []
            if character_count_by_shot.get(shot.id):
                parts.append(f"{character_count_by_shot[shot.id]} 个自动人物候选")
            if scene_by_shot.get(shot.id):
                parts.append("已归入自动场景候选")
            if dialogue_count_by_shot.get(shot.id):
                parts.append(f"{dialogue_count_by_shot[shot.id]} 段源对白")
            shot.short_description = "；".join(parts) if parts else "暂无需要结构化控制的自动结果"

        previous = session.scalars(select(ContentAnalysisRun).where(
            ContentAnalysisRun.project_id == project_id, ContentAnalysisRun.is_current.is_(True)
        )).all()
        for item in previous:
            item.is_current = False
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            raise ContentAnalysisError("F05 Run 记录丢失")
        warnings = any(value not in {"READY", "NO_DIALOGUE", "NO_SPEECH"} for value in component_status.values())
        run.status = "READY_WITH_WARNINGS" if warnings else "READY"
        run.is_current = True
        run.component_status_json = json.dumps(component_status, ensure_ascii=False)
        run.counts_json = json.dumps({
            "character_candidates": len(candidates), "character_tracks": sum(len(item.tracks) for item in candidates),
            "scene_candidates": len(scenes), "prop_candidates": 0,
            "dialogues": len(dialogues), "speaker_segments": len(speaker_segments),
        }, ensure_ascii=False)
        run.completed_at = utcnow()
        session.commit()


def run_content_analysis(project_id: str) -> dict[str, Any]:
    project, episodes, shots = _load_context(project_id)
    run_id = _create_run(project_id)
    component_status: dict[str, str] = {
        "characters": "PENDING", "scenes": "PENDING", "props": "NOT_CONFIGURED",
        "asr": "PENDING", "speaker": "PENDING", "speaker_character": "PENDING",
        "description": "BASIC",
    }
    try:
        candidates: list[CandidateDraft] = []
        try:
            observations = _detect_character_observations(shots)
            candidates = _cluster_characters(_build_tracks(observations))
            component_status["characters"] = "READY" if candidates else "NO_CHARACTER"
        except (ContentModelError, ImportError) as exc:
            component_status["characters"] = "MODEL_NOT_READY"
            component_status["characters_detail"] = str(exc)

        scenes = _cluster_scenes(run_id, project_id, shots)
        component_status["scenes"] = "READY" if scenes else "NO_SCENE"

        try:
            asr_status, dialogues = _run_asr(project, episodes, shots)
        except Exception as exc:
            asr_status, dialogues = "FAILED", []
            component_status["asr_detail"] = str(exc)
        component_status["asr"] = asr_status

        try:
            speaker_status, speaker_segments = _run_diarization(episodes)
        except Exception as exc:
            speaker_status, speaker_segments = "FAILED", []
            component_status["speaker_detail"] = str(exc)
        component_status["speaker"] = speaker_status

        _attach_speakers(dialogues, speaker_segments)
        _map_speaker_to_character(dialogues, candidates)
        mapped = sum(1 for item in dialogues if item.get("speaker_candidate_id"))
        component_status["speaker_character"] = "READY" if mapped else ("NO_MAPPING" if dialogues else "NO_DIALOGUE")

        _persist_results(
            run_id=run_id, project_id=project_id, shots=shots, candidates=candidates, scenes=scenes,
            dialogues=dialogues, speaker_segments=speaker_segments, component_status=component_status,
        )
        return get_analysis_run(run_id) or {"id": run_id, "status": "READY"}
    except Exception as exc:
        _fail_run(run_id, str(exc))
        raise


def _serialize_run(run: ContentAnalysisRun) -> dict[str, Any]:
    return {
        "id": run.id, "project_id": run.project_id, "status": run.status, "is_current": run.is_current,
        "profile_version": run.profile_version,
        "component_status": json.loads(run.component_status_json or "{}"),
        "counts": json.loads(run.counts_json or "{}"), "error_message": run.error_message,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def get_analysis_run(run_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            return None
        payload = _serialize_run(run)
        characters = session.scalars(select(CharacterCandidate).where(CharacterCandidate.run_id == run_id).order_by(CharacterCandidate.ordinal)).all()
        tracks = session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run_id)).all()
        tracks_by_candidate: dict[str, list[CharacterTrack]] = {}
        for track in tracks:
            tracks_by_candidate.setdefault(track.candidate_id, []).append(track)
        payload["characters"] = [{
            "id": item.id, "ordinal": item.ordinal, "auto_label": item.auto_label,
            "track_count": item.track_count, "shot_count": item.shot_count, "confidence": item.confidence,
            "cover_url": f"/api/content-analysis/characters/{item.id}/cover" if item.cover_path else None,
            "tracks": [{
                "id": track.id, "shot_id": track.shot_id, "start_us": track.start_us, "end_us": track.end_us,
                "representative_source_us": track.representative_source_us,
                "bbox": json.loads(track.bbox_json), "sample_count": track.sample_count,
                "face_visible": track.face_visible, "mean_face_score": track.mean_face_score,
            } for track in tracks_by_candidate.get(item.id, [])],
        } for item in characters]

        scenes = session.scalars(select(SceneCandidate).where(SceneCandidate.run_id == run_id).order_by(SceneCandidate.ordinal)).all()
        scene_links = session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)).all()
        links_by_scene: dict[str, list[str]] = {}
        for link in scene_links:
            links_by_scene.setdefault(link.scene_candidate_id, []).append(link.shot_id)
        payload["scenes"] = [{
            "id": item.id, "ordinal": item.ordinal, "auto_label": item.auto_label, "shot_count": item.shot_count,
            "cover_url": f"/api/content-analysis/scenes/{item.id}/cover" if item.cover_path else None,
            "shot_ids": links_by_scene.get(item.id, []),
        } for item in scenes]

        dialogues = session.scalars(select(AnalysisDialogue).where(AnalysisDialogue.run_id == run_id).order_by(AnalysisDialogue.episode_id, AnalysisDialogue.source_start_us)).all()
        payload["dialogues"] = [{
            "id": item.id, "episode_id": item.episode_id, "shot_id": item.shot_id,
            "source_start_us": item.source_start_us, "source_end_us": item.source_end_us,
            "shot_start_us": item.shot_start_us, "shot_end_us": item.shot_end_us,
            "ai_text": item.ai_text, "language": item.language, "speaker_label": item.speaker_label,
            "speaker_candidate_id": item.speaker_candidate_id,
            "speaker_mapping_confidence": item.speaker_mapping_confidence,
            "dialogue_type": item.dialogue_type, "emotion": item.emotion, "speaking_style": item.speaking_style,
        } for item in dialogues]
        payload["props"] = []
        return payload


def get_current_analysis(project_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        run = session.scalar(select(ContentAnalysisRun).where(
            ContentAnalysisRun.project_id == project_id, ContentAnalysisRun.is_current.is_(True)
        ).order_by(ContentAnalysisRun.completed_at.desc()))
        run_id = run.id if run else None
    return get_analysis_run(run_id) if run_id else None


def get_candidate_cover(candidate_id: str, entity_type: str) -> Path | None:
    with get_session() as session:
        if entity_type == "character":
            item = session.get(CharacterCandidate, candidate_id)
        elif entity_type == "scene":
            item = session.get(SceneCandidate, candidate_id)
        else:
            return None
        raw = item.cover_path if item else None
        return Path(raw) if raw else None


def content_model_status() -> dict[str, object]:
    return model_status()
