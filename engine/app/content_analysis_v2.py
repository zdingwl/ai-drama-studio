"""F05「智能内容识别」V2。

F05 只保存 AI Evidence，不直接写人工 Final Character / Scene / Prop / Dialogue。
Reference Clip 继续负责动作、机位、构图和运动；本模块重点保存重制时必须控制的语义。

当前能力：
- Character Identity / Track：YuNet + SFace + body-only HOG + 身体/服装颜色证据；
- Scene：Shot Thumbnail 视觉聚类；
- ASR：faster-whisper；
- Speaker：可选本地 pyannote Pipeline；
- Speaker → Character：基于跨 Shot 共现做保守映射；
- Key Prop：数据边界已建立，未配置对象模型时绝不伪造结果；
- Short Description：只生成结构化摘要，不复述 Reference Video 已经包含的动作/摄影细节。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.character_visual_v2 import (
    CandidateDraft,
    TrackDraft,
    analyze_characters,
    cosine,
    mean_vector,
    save_candidate_cover,
)
from engine.app.content_models_v2 import ContentModelError, model_status
from engine.app.studio_v2 import Base, Episode, Project, Shot, get_session, new_id, utcnow

PROFILE_VERSION = "f05-v2.2"
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
class SceneDraft:
    id: str
    shot_ids: list[str] = field(default_factory=list)
    centroid: Any | None = None
    cover_path: str | None = None
    scores: list[float] = field(default_factory=list)


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
    descriptors = {shot["id"]: _scene_descriptor(shot.get("thumbnail_path")) for shot in shots}
    scenes: list[SceneDraft] = []
    for shot in shots:
        descriptor = descriptors.get(shot["id"])
        if descriptor is None:
            continue
        best: SceneDraft | None = None
        best_score = -1.0
        for scene in scenes:
            score = cosine(scene.centroid, descriptor) or -1.0
            if score >= SCENE_CLUSTER_THRESHOLD and score > best_score:
                best, best_score = scene, score
        if best is None:
            best = SceneDraft(id=new_id("SCENE_CANDIDATE"), cover_path=shot.get("thumbnail_path"))
            scenes.append(best)
        else:
            best.scores.append(best_score)
        best.shot_ids.append(shot["id"])
        best.centroid = mean_vector([descriptors[shot_id] for shot_id in best.shot_ids if descriptors.get(shot_id) is not None])
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
        actual_device = device
    except Exception:
        if device != "cuda":
            raise
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        actual_device = "cpu"

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
            best_shot = None
            best_overlap = 0
            for shot in shots_by_episode.get(episode["id"], []):
                overlap = max(0, min(end_us, shot["end_us"]) - max(start_us, shot["start_us"]))
                if overlap > best_overlap:
                    best_overlap, best_shot = overlap, shot
            if best_shot is None:
                continue
            results.append({
                "id": new_id("AI_DIALOGUE"),
                "episode_id": episode["id"],
                "shot_id": best_shot["id"],
                "source_start_us": start_us,
                "source_end_us": end_us,
                "shot_start_us": max(0, start_us - best_shot["start_us"]),
                "shot_end_us": min(best_shot["duration_us"], max(1, end_us - best_shot["start_us"])),
                "ai_text": text,
                "language": getattr(info, "language", None),
                "speaker_label": None,
                "speaker_candidate_id": None,
                "speaker_mapping_confidence": None,
                "dialogue_type": "unknown",
                "emotion": None,
                "speaking_style": None,
                "confidence": None,
                "evidence": {"provider": "faster-whisper", "model": model_name, "device": actual_device},
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
        diarization = getattr(result, "exclusive_speaker_diarization", None)
        if diarization is None:
            diarization = getattr(result, "speaker_diarization", result)
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            output.append({
                "id": new_id("SPEAKER_SEGMENT"),
                "episode_id": episode["id"],
                "start_us": int(round(float(turn.start) * 1_000_000)),
                "end_us": int(round(float(turn.end) * 1_000_000)),
                "speaker_label": str(speaker),
                "confidence": None,
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
            overlap = max(
                0,
                min(dialogue["source_end_us"], segment["end_us"])
                - max(dialogue["source_start_us"], segment["start_us"]),
            )
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
        for candidate_id in candidates_by_shot.get(dialogue["shot_id"], set()):
            score_bucket = scores.setdefault(speaker, {})
            score_bucket[candidate_id] = score_bucket.get(candidate_id, 0) + 1

    mapping: dict[str, tuple[str, float]] = {}
    for speaker, candidate_scores in scores.items():
        ordered = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
        if not ordered:
            continue
        candidate_id, count = ordered[0]
        second = ordered[1][1] if len(ordered) > 1 else 0
        confidence = count / max(1, totals.get(speaker, 1))
        if count >= 2 and confidence >= 0.60 and count > second:
            mapping[speaker] = (candidate_id, min(0.90, confidence))

    for dialogue in dialogues:
        speaker = dialogue.get("speaker_label")
        if speaker in mapping:
            dialogue["speaker_candidate_id"], dialogue["speaker_mapping_confidence"] = mapping[speaker]
            dialogue["dialogue_type"] = "dialogue"
            continue
        if speaker:
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
                "id": episode.id,
                "sort_order": episode.sort_order,
                "audio_path": preprocess.audio_path if preprocess else None,
            })
            for shot in episode_shots:
                shots.append({
                    "id": shot.id,
                    "episode_id": episode.id,
                    "episode_order": episode.sort_order,
                    "ordinal": shot.ordinal,
                    "start_us": shot.start_us,
                    "end_us": shot.end_us,
                    "duration_us": shot.duration_us,
                    "reference_path": shot.reference_clip_path,
                    "thumbnail_path": shot.thumbnail_path,
                })
        return (
            {
                "id": project.id,
                "source_language": project.source_language,
                "target_language": project.target_language,
                "target_region": project.target_region,
            },
            episode_payloads,
            shots,
        )


def _create_run(project_id: str) -> str:
    run_id = new_id("CONTENT_RUN")
    with get_session() as session:
        session.add(ContentAnalysisRun(
            id=run_id,
            project_id=project_id,
            status="PROCESSING",
            is_current=False,
            profile_version=PROFILE_VERSION,
            component_status_json="{}",
            counts_json="{}",
        ))
        session.commit()
    return run_id


def _fail_run(run_id: str, message: str) -> None:
    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is not None:
            run.status = "FAILED"
            run.error_message = message
            run.completed_at = utcnow()
            session.commit()


def _persist_results(
    *,
    run_id: str,
    project_id: str,
    shots: list[dict[str, Any]],
    candidates: list[CandidateDraft],
    scenes: list[SceneDraft],
    dialogues: list[dict[str, Any]],
    speaker_segments: list[dict[str, Any]],
    component_status: dict[str, str],
) -> None:
    scene_by_shot: dict[str, str] = {}
    with get_session() as session:
        for ordinal, candidate in enumerate(candidates, start=1):
            cover_path = save_candidate_cover(run_id, candidate, ordinal)
            confidence = sum(candidate.scores) / len(candidate.scores) if candidate.scores else None
            face_track_count = sum(1 for track in candidate.tracks if any(obs.face_visible for obs in track.observations))
            session.add(CharacterCandidate(
                id=candidate.id,
                run_id=run_id,
                project_id=project_id,
                ordinal=ordinal,
                auto_label=f"人物 {ordinal:03d}",
                track_count=len(candidate.tracks),
                shot_count=len({item.shot_id for item in candidate.tracks}),
                confidence=confidence,
                cover_path=cover_path,
                evidence_json=json.dumps({
                    "identity": "YuNet + SFace + body-only HOG + clothing histogram",
                    "face_track_count": face_track_count,
                    "body_only_track_count": len(candidate.tracks) - face_track_count,
                    "profile": PROFILE_VERSION,
                }, ensure_ascii=False),
            ))
            for track in candidate.tracks:
                representative = max(track.observations, key=lambda item: (1 if item.face_visible else 0, item.detection_score))
                face_scores = [item.detection_score for item in track.observations if item.face_visible]
                body_scores = [cosine(track.body_hist, item.body_hist) for item in track.observations if item.body_hist is not None]
                valid_body_scores = [value for value in body_scores if value is not None]
                session.add(CharacterTrack(
                    id=new_id("CHAR_TRACK"),
                    run_id=run_id,
                    candidate_id=candidate.id,
                    shot_id=track.shot_id,
                    start_us=min(item.source_time_us for item in track.observations),
                    end_us=max(item.source_time_us for item in track.observations) + 1,
                    representative_source_us=representative.source_time_us,
                    bbox_json=json.dumps(list(representative.bbox)),
                    sample_count=len(track.observations),
                    face_visible=any(item.face_visible for item in track.observations),
                    mean_face_score=sum(face_scores) / len(face_scores) if face_scores else None,
                    body_evidence_score=sum(valid_body_scores) / len(valid_body_scores) if valid_body_scores else None,
                    evidence_json=json.dumps({
                        "samples": [
                            {
                                "source_time_us": item.source_time_us,
                                "bbox": list(item.bbox),
                                "face_bbox": list(item.face_bbox) if item.face_bbox else None,
                                "score": item.detection_score,
                                "face_visible": item.face_visible,
                            }
                            for item in track.observations
                        ]
                    }, ensure_ascii=False),
                ))

        for ordinal, scene in enumerate(scenes, start=1):
            session.add(SceneCandidate(
                id=scene.id,
                run_id=run_id,
                project_id=project_id,
                ordinal=ordinal,
                auto_label=f"场景 {ordinal:03d}",
                shot_count=len(scene.shot_ids),
                cover_path=scene.cover_path,
                evidence_json=json.dumps({"method": "HSV visual clustering", "profile": PROFILE_VERSION}, ensure_ascii=False),
            ))
            scene_confidence = sum(scene.scores) / len(scene.scores) if scene.scores else 1.0
            for shot_id in scene.shot_ids:
                scene_by_shot[shot_id] = scene.id
                session.add(ShotSceneEvidence(
                    id=new_id("SHOT_SCENE"),
                    run_id=run_id,
                    shot_id=shot_id,
                    scene_candidate_id=scene.id,
                    confidence=scene_confidence,
                ))

        for item in speaker_segments:
            session.add(SpeakerSegment(
                id=item["id"],
                run_id=run_id,
                episode_id=item["episode_id"],
                start_us=item["start_us"],
                end_us=item["end_us"],
                speaker_label=item["speaker_label"],
                confidence=item.get("confidence"),
            ))
        for item in dialogues:
            session.add(AnalysisDialogue(
                id=item["id"],
                run_id=run_id,
                episode_id=item["episode_id"],
                shot_id=item["shot_id"],
                source_start_us=item["source_start_us"],
                source_end_us=item["source_end_us"],
                shot_start_us=item["shot_start_us"],
                shot_end_us=item["shot_end_us"],
                ai_text=item["ai_text"],
                language=item.get("language"),
                speaker_label=item.get("speaker_label"),
                speaker_candidate_id=item.get("speaker_candidate_id"),
                speaker_mapping_confidence=item.get("speaker_mapping_confidence"),
                dialogue_type=item.get("dialogue_type") or "unknown",
                emotion=item.get("emotion"),
                speaking_style=item.get("speaking_style"),
                confidence=item.get("confidence"),
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
                parts.append(f"{character_count_by_shot[shot.id]} 个人物候选")
            if scene_by_shot.get(shot.id):
                parts.append("已归入场景候选")
            if dialogue_count_by_shot.get(shot.id):
                parts.append(f"{dialogue_count_by_shot[shot.id]} 段源对白")
            shot.short_description = "；".join(parts) if parts else "暂无需要结构化控制的自动结果"

        for previous in session.scalars(select(ContentAnalysisRun).where(
            ContentAnalysisRun.project_id == project_id,
            ContentAnalysisRun.is_current.is_(True),
        )).all():
            previous.is_current = False

        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            raise ContentAnalysisError("F05 Run 记录丢失")
        normal_statuses = {"READY", "NO_DIALOGUE", "NO_SPEECH", "NO_CHARACTER", "NO_SCENE", "BASIC"}
        core_values = [component_status.get(key, "") for key in ("characters", "scenes", "props", "asr", "speaker", "speaker_character", "description")]
        warnings = any(value not in normal_statuses for value in core_values)
        run.status = "READY_WITH_WARNINGS" if warnings else "READY"
        run.is_current = True
        run.component_status_json = json.dumps(component_status, ensure_ascii=False)
        run.counts_json = json.dumps({
            "character_candidates": len(candidates),
            "character_tracks": sum(len(item.tracks) for item in candidates),
            "scene_candidates": len(scenes),
            "prop_candidates": 0,
            "dialogues": len(dialogues),
            "speaker_segments": len(speaker_segments),
        }, ensure_ascii=False)
        run.completed_at = utcnow()
        session.commit()


def run_content_analysis(project_id: str) -> dict[str, Any]:
    project, episodes, shots = _load_context(project_id)
    run_id = _create_run(project_id)
    component_status: dict[str, str] = {
        "characters": "PENDING",
        "scenes": "PENDING",
        "props": "NOT_CONFIGURED",
        "asr": "PENDING",
        "speaker": "PENDING",
        "speaker_character": "PENDING",
        "description": "BASIC",
    }
    try:
        candidates: list[CandidateDraft] = []
        try:
            candidates = analyze_characters(shots)
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
            run_id=run_id,
            project_id=project_id,
            shots=shots,
            candidates=candidates,
            scenes=scenes,
            dialogues=dialogues,
            speaker_segments=speaker_segments,
            component_status=component_status,
        )
        return get_analysis_run(run_id) or {"id": run_id, "status": "READY"}
    except Exception as exc:
        _fail_run(run_id, str(exc))
        raise


def _serialize_run(run: ContentAnalysisRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "is_current": run.is_current,
        "profile_version": run.profile_version,
        "component_status": json.loads(run.component_status_json or "{}"),
        "counts": json.loads(run.counts_json or "{}"),
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def get_analysis_run(run_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            return None
        payload = _serialize_run(run)

        characters = session.scalars(select(CharacterCandidate).where(
            CharacterCandidate.run_id == run_id
        ).order_by(CharacterCandidate.ordinal)).all()
        tracks = session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run_id)).all()
        tracks_by_candidate: dict[str, list[CharacterTrack]] = {}
        for track in tracks:
            tracks_by_candidate.setdefault(track.candidate_id, []).append(track)
        payload["characters"] = [
            {
                "id": item.id,
                "ordinal": item.ordinal,
                "auto_label": item.auto_label,
                "track_count": item.track_count,
                "shot_count": item.shot_count,
                "confidence": item.confidence,
                "cover_url": f"/api/content-analysis/characters/{item.id}/cover" if item.cover_path else None,
                "tracks": [
                    {
                        "id": track.id,
                        "shot_id": track.shot_id,
                        "start_us": track.start_us,
                        "end_us": track.end_us,
                        "representative_source_us": track.representative_source_us,
                        "bbox": json.loads(track.bbox_json),
                        "sample_count": track.sample_count,
                        "face_visible": track.face_visible,
                        "mean_face_score": track.mean_face_score,
                    }
                    for track in tracks_by_candidate.get(item.id, [])
                ],
            }
            for item in characters
        ]

        scenes = session.scalars(select(SceneCandidate).where(
            SceneCandidate.run_id == run_id
        ).order_by(SceneCandidate.ordinal)).all()
        scene_links = session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)).all()
        links_by_scene: dict[str, list[str]] = {}
        for link in scene_links:
            links_by_scene.setdefault(link.scene_candidate_id, []).append(link.shot_id)
        payload["scenes"] = [
            {
                "id": item.id,
                "ordinal": item.ordinal,
                "auto_label": item.auto_label,
                "shot_count": item.shot_count,
                "cover_url": f"/api/content-analysis/scenes/{item.id}/cover" if item.cover_path else None,
                "shot_ids": links_by_scene.get(item.id, []),
            }
            for item in scenes
        ]

        dialogues = session.scalars(select(AnalysisDialogue).where(
            AnalysisDialogue.run_id == run_id
        ).order_by(AnalysisDialogue.episode_id, AnalysisDialogue.source_start_us)).all()
        payload["dialogues"] = [
            {
                "id": item.id,
                "episode_id": item.episode_id,
                "shot_id": item.shot_id,
                "source_start_us": item.source_start_us,
                "source_end_us": item.source_end_us,
                "shot_start_us": item.shot_start_us,
                "shot_end_us": item.shot_end_us,
                "ai_text": item.ai_text,
                "language": item.language,
                "speaker_label": item.speaker_label,
                "speaker_candidate_id": item.speaker_candidate_id,
                "speaker_mapping_confidence": item.speaker_mapping_confidence,
                "dialogue_type": item.dialogue_type,
                "emotion": item.emotion,
                "speaking_style": item.speaking_style,
            }
            for item in dialogues
        ]
        payload["props"] = []
        return payload


def get_current_analysis(project_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        run = session.scalar(select(ContentAnalysisRun).where(
            ContentAnalysisRun.project_id == project_id,
            ContentAnalysisRun.is_current.is_(True),
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
