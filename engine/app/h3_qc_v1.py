"""R9 H3 QC, automatic retry and selected-output orchestration.

The generation layer answers "did H3 produce a file?". This layer answers "is that file safe to
become the current localized remake output?". It combines deterministic media checks with the
existing local Qwen3-VL service. Only PASS outputs are auto-selected. Runtime/model unavailability
stays operational state; repeated content-quality failures become H3_QC ReviewIssues.
"""
from __future__ import annotations

import base64
from datetime import datetime
import json
import mimetypes
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.asset_semantics_v3 import semantic_model_status
from engine.app.generation_attempt_v1 import (
    GenerationAttempt,
    GenerationAttemptError,
    execute_generation_segment_v1,
    get_generation_attempt_v1,
)
from engine.app.generation_segment_v1 import compile_generation_segments_v1, get_generation_segments_v1
from engine.app.generation_selection_v1 import (
    list_generation_selections_v1,
    selected_generation_output_v1,
    set_generation_selection_v1,
)
from engine.app.h3_qc_contract_v1 import (
    GenerationQualityCheckV1,
    GenerationQualityProjectSummaryV1,
    GenerationSemanticQCV1,
    GenerationStructuralQCV1,
)
from engine.app.h3_reference_assets_v1 import ensure_target_character_references_v1, ensure_target_scene_references_v1
from engine.app.review_issue_v1 import upsert_review_issue
from engine.app.studio_v2 import Base, Project, get_session, new_id, project_dir, utcnow


QC_PROFILE_VERSION = "H3_QC_V1"
VISUAL_INTEGRITY_MIN = 0.80
CHARACTER_CONSISTENCY_MIN = 0.72
SCENE_CONSISTENCY_MIN = 0.72
ACTION_CAMERA_MIN = 0.68
CONTINUITY_MIN = 0.72
SEMANTIC_CONFIDENCE_MIN = 0.55
CRITICAL_RETRY_THRESHOLD = 0.45


class H3QualityError(RuntimeError):
    pass


class GenerationQualityCheck(Base):
    __tablename__ = "v2_generation_quality_checks"
    __table_args__ = (
        UniqueConstraint("generation_attempt_id", name="uq_v2_generation_quality_attempt"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    generation_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_segments.id", ondelete="CASCADE"), index=True)
    generation_attempt_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_attempts.id", ondelete="CASCADE"), unique=True, index=True)
    segment_input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False, default=QC_PROFILE_VERSION)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    structural_json: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_profile: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    retry_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _serialize(row: GenerationQualityCheck) -> dict[str, Any]:
    return GenerationQualityCheckV1.model_validate({
        "id": row.id,
        "project_id": row.project_id,
        "episode_id": row.episode_id,
        "generation_segment_id": row.generation_segment_id,
        "generation_attempt_id": row.generation_attempt_id,
        "segment_input_fingerprint": row.segment_input_fingerprint,
        "profile_version": row.profile_version,
        "status": row.status,
        "quality_score": row.quality_score,
        "structural": _json(row.structural_json, {}),
        "semantic": _json(row.semantic_json, None),
        "model_profile": row.model_profile,
        "reason": row.reason,
        "retry_instruction": row.retry_instruction,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }).model_dump(mode="json")


def _current_segments(project_id: str) -> dict[str, dict[str, Any]]:
    plan = get_generation_segments_v1(project_id)
    return {
        str(segment["id"]): dict(segment)
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("id")
    }


def _current_segment(project_id: str, segment_id: str) -> dict[str, Any]:
    segment = _current_segments(project_id).get(segment_id)
    if segment is None:
        raise LookupError("GenerationSegment 不存在或已经失效")
    return segment


def _run(command: list[str], *, timeout_seconds: int = 1200) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise H3QualityError(f"找不到 {command[0]}，无法执行 H3 QC") from exc
    except subprocess.TimeoutExpired as exc:
        raise H3QualityError("H3 QC 媒体检查超时") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-3500:]
        raise H3QualityError(detail or f"{command[0]} 执行失败") from exc


def _parse_fps(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw or raw in {"0/0", "N/A"}:
        return None
    try:
        if "/" in raw:
            numerator, denominator = raw.split("/", 1)
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else None
        return float(raw)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def structural_h3_qc_v1(path: Path, *, expected_duration_us: int) -> dict[str, Any]:
    """Deterministic gate: valid video stream, full decode and target-duration match."""

    expected = max(1, int(expected_duration_us))
    base = {
        "expected_duration_us": expected,
        "actual_duration_us": None,
        "duration_delta_us": None,
        "duration_tolerance_us": 250_000,
        "duration_ok": False,
        "decode_ok": False,
        "has_video": False,
        "width": None,
        "height": None,
        "fps": None,
        "error_message": None,
    }
    if not path.is_file() or path.stat().st_size <= 0:
        base["error_message"] = "H3 输出文件不存在或为空"
        return GenerationStructuralQCV1.model_validate(base).model_dump(mode="json")

    try:
        result = _run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of", "json", str(path),
        ], timeout_seconds=180)
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams") or []
        video = next((item for item in streams if isinstance(item, Mapping) and item.get("codec_type") == "video"), None)
        duration_raw = (payload.get("format") or {}).get("duration") if isinstance(payload.get("format"), Mapping) else None
        actual = int(round(float(duration_raw) * 1_000_000)) if duration_raw not in (None, "N/A", "") else None
        fps = _parse_fps(video.get("avg_frame_rate")) if isinstance(video, Mapping) else None
        tolerance = max(180_000, int(round(3_000_000 / fps))) if fps and fps > 0 else 250_000
        delta = actual - expected if actual is not None else None
        base.update({
            "actual_duration_us": actual,
            "duration_delta_us": delta,
            "duration_tolerance_us": tolerance,
            "duration_ok": actual is not None and abs(delta or 0) <= tolerance,
            "has_video": video is not None,
            "width": int(video.get("width") or 0) or None if isinstance(video, Mapping) else None,
            "height": int(video.get("height") or 0) or None if isinstance(video, Mapping) else None,
            "fps": fps,
        })
        if video is None:
            base["error_message"] = "H3 输出没有视频流"
            return GenerationStructuralQCV1.model_validate(base).model_dump(mode="json")
        _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], timeout_seconds=1200)
        base["decode_ok"] = True
        if not base["duration_ok"]:
            base["error_message"] = f"H3 输出时长偏差 {delta or 0}us，超过允许误差 {tolerance}us"
    except (H3QualityError, ValueError, TypeError, json.JSONDecodeError) as exc:
        base["error_message"] = str(exc)[:3500]
    return GenerationStructuralQCV1.model_validate(base).model_dump(mode="json")


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _file_uri_path(value: str) -> Path | None:
    raw = value.strip()
    if not raw.startswith("file://"):
        return None
    parsed = urlparse(raw)
    path = Path(unquote(parsed.path))
    if parsed.netloc and not path.drive:
        path = Path(f"//{parsed.netloc}{path}")
    return path


def _extract_frame(video: Path, seconds: float, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{max(0.0, seconds):.6f}", "-i", str(video),
        "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", "2", str(output),
    ], timeout_seconds=300)
    if not output.is_file() or output.stat().st_size <= 0:
        raise H3QualityError("H3 QC 抽帧失败")
    return output


def _sample_video(video: Path, duration_us: int, root: Path, prefix: str) -> list[Path]:
    seconds = max(0.05, duration_us / 1_000_000)
    points = [max(0.0, seconds * ratio) for ratio in (0.15, 0.50, 0.85)]
    return [_extract_frame(video, point, root / f"{prefix}-{index}.jpg") for index, point in enumerate(points, start=1)]


def _clamp_score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _extract_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise H3QualityError("Qwen3-VL QC 没有返回 JSON")
    try:
        payload = json.loads(value[start : end + 1])
    except json.JSONDecodeError as exc:
        raise H3QualityError("Qwen3-VL QC JSON 无法解析") from exc
    if not isinstance(payload, dict):
        raise H3QualityError("Qwen3-VL QC 返回的不是 JSON object")
    return payload


def _semantic_prompt(segment: Mapping[str, Any], labels: list[str]) -> str:
    characters = [
        {
            "target_name": item.get("target_name"),
            "appearance_profile": item.get("appearance_profile"),
        }
        for item in segment.get("target_characters") or []
        if isinstance(item, Mapping)
    ]
    scene = segment.get("target_scene") if isinstance(segment.get("target_scene"), Mapping) else None
    facts = {
        "generation_mode": segment.get("generation_mode"),
        "visual_description": segment.get("visual_description"),
        "performance": segment.get("performance") or [],
        "cinematography": segment.get("cinematography") or {},
        "target_characters": characters,
        "target_scene": scene,
        "labels": labels,
    }
    return (
        "你是短剧出海重拍的 H3 成片质检器。只返回 JSON，不要解释。"
        "GENERATED_* 是待质检新视频；TARGET_CHARACTER_* 是目标演员身份参考；TARGET_SCENE 是本土化目标场景参考；"
        "SOURCE_* 只用于比较动作顺序、走位、构图和镜头，不允许把 SOURCE_* 中的原演员身份当成正确人物；"
        "CONTINUITY_FIRST_FRAME 是上一条已通过 QC 的连续首帧。"
        "请判断：1) 新视频是否有明显畸形、融脸、额外肢体、人物突然变脸/消失等生成崩坏；"
        "2) 可见人物是否保持 TARGET_CHARACTER 目标身份而不是 SOURCE 原演员；"
        "3) LOCALIZE 场景是否符合 TARGET_SCENE/目标描述；KEEP 场景是否合理保持原空间；"
        "4) Ref2VA 时动作顺序、走位、构图和镜头运动是否与 SOURCE 参考一致；"
        "5) 有连续首帧时是否自然承接。不要评价最终口型同步，口型属于后续 Lip Sync QC。"
        "分数 0..1。信息不足时 confidence 降低，不要虚构。"
        "严格返回：{"
        "\"visual_integrity\":0.0,"
        "\"target_character_consistency\":null,"
        "\"scene_consistency\":null,"
        "\"action_camera_consistency\":null,"
        "\"continuity_consistency\":null,"
        "\"confidence\":0.0,"
        "\"source_actor_leak\":false,"
        "\"obvious_visual_artifact\":false,"
        "\"reasons\":[\"\"],"
        "\"retry_instruction\":\"给下一次 H3 重试的具体英文修正指令\"}。"
        f"业务事实：{json.dumps(facts, ensure_ascii=False)}"
    )


def _request_semantic_qc(prompt: str, labeled_images: list[tuple[str, Path]]) -> tuple[dict[str, Any], str]:
    status = semantic_model_status()
    if not status.get("ready"):
        raise H3QualityError("Qwen3-VL 本地服务未配置")
    base_url = str(status["base_url"])
    model = str(status["model"])
    api_key = os.getenv("AI_DRAMA_VLM_API_KEY", "EMPTY").strip() or "EMPTY"
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for label, path in labeled_images:
        content.append({"type": "text", "text": label})
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(path)}})
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=240.0) as client:
            response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        raw_content = body["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise H3QualityError(f"Qwen3-VL H3 QC 请求失败：{exc}") from exc
    if isinstance(raw_content, list):
        raw_content = "".join(str(item.get("text") or "") for item in raw_content if isinstance(item, dict))
    return _extract_json(str(raw_content)), f"openai-compatible:{model}"


def semantic_qc_policy_v1(raw: Mapping[str, Any], segment: Mapping[str, Any]) -> tuple[str, float | None, dict[str, Any], str, str | None]:
    semantic = {
        "visual_integrity": _clamp_score(raw.get("visual_integrity")),
        "target_character_consistency": _clamp_score(raw.get("target_character_consistency")),
        "scene_consistency": _clamp_score(raw.get("scene_consistency")),
        "action_camera_consistency": _clamp_score(raw.get("action_camera_consistency")),
        "continuity_consistency": _clamp_score(raw.get("continuity_consistency")),
        "confidence": _clamp_score(raw.get("confidence")),
        "source_actor_leak": _bool(raw.get("source_actor_leak")),
        "obvious_visual_artifact": _bool(raw.get("obvious_visual_artifact")),
        "reasons": [str(item).strip() for item in (raw.get("reasons") or []) if str(item).strip()][:12],
        "retry_instruction": str(raw.get("retry_instruction") or "").strip()[:4000] or None,
        "raw": dict(raw),
    }
    validated = GenerationSemanticQCV1.model_validate(semantic).model_dump(mode="json")
    required: list[tuple[str, float]] = [("visual_integrity", VISUAL_INTEGRITY_MIN)]
    if segment.get("target_characters"):
        required.append(("target_character_consistency", CHARACTER_CONSISTENCY_MIN))
    scene = segment.get("target_scene") if isinstance(segment.get("target_scene"), Mapping) else None
    if scene is not None:
        required.append(("scene_consistency", SCENE_CONSISTENCY_MIN))
    if segment.get("generation_mode") == "REF2VA":
        required.append(("action_camera_consistency", ACTION_CAMERA_MIN))
    if segment.get("continuity_from_segment_id"):
        required.append(("continuity_consistency", CONTINUITY_MIN))

    missing = [name for name, _threshold in required if validated.get(name) is None]
    confidence = validated.get("confidence")
    values = [float(validated[name]) for name, _ in required if validated.get(name) is not None]
    score = sum(values) / len(values) if values else None
    reasons = list(validated.get("reasons") or [])
    retry_instruction = validated.get("retry_instruction")

    if missing:
        raise H3QualityError("Qwen3-VL H3 QC 缺少必要评分：" + "、".join(missing))
    if confidence is None:
        raise H3QualityError("Qwen3-VL H3 QC 缺少 confidence")
    if validated["source_actor_leak"]:
        return "RETRY", score, validated, "检测到原演员身份泄漏到目标视频", retry_instruction or "Replace every visible source actor with the target character identity references; preserve only source blocking and camera motion."
    if validated["obvious_visual_artifact"]:
        return "RETRY", score, validated, "检测到明显 H3 生成崩坏或人物结构异常", retry_instruction or "Remove visible generation artifacts, identity morphing and anatomy errors while preserving the planned shot."
    if confidence < SEMANTIC_CONFIDENCE_MIN:
        return "REVIEW", score, validated, "自动视觉质检置信度不足，需要人工查看已有版本", retry_instruction

    failed = [(name, float(validated[name]), threshold) for name, threshold in required if float(validated[name]) < threshold]
    if not failed:
        return "PASS", score, validated, "H3 结构与语义质检通过", None
    if any(value < CRITICAL_RETRY_THRESHOLD for _name, value, _threshold in failed):
        reason = "；".join(f"{name}={value:.2f}<{threshold:.2f}" for name, value, threshold in failed)
        return "RETRY", score, validated, "H3 关键质量明显不达标：" + reason, retry_instruction
    reason = "；".join(f"{name}={value:.2f}<{threshold:.2f}" for name, value, threshold in failed)
    return "RETRY", score, validated, "H3 质量未达到自动通过阈值：" + reason, retry_instruction


def _persist_qc(
    attempt: Mapping[str, Any],
    *,
    status: str,
    structural: Mapping[str, Any],
    semantic: Mapping[str, Any] | None,
    quality_score: float | None,
    model_profile: str | None,
    reason: str,
    retry_instruction: str | None,
) -> dict[str, Any]:
    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(GenerationQualityCheck).where(
            GenerationQualityCheck.generation_attempt_id == str(attempt["id"])
        ))
        if row is None:
            row = GenerationQualityCheck(
                id=new_id("H3QC"),
                project_id=str(attempt["project_id"]),
                episode_id=str(attempt["episode_id"]),
                generation_segment_id=str(attempt["generation_segment_id"]),
                generation_attempt_id=str(attempt["id"]),
                segment_input_fingerprint=str(attempt["segment_input_fingerprint"]),
                profile_version=QC_PROFILE_VERSION,
                status=status,
                quality_score=quality_score,
                structural_json=json.dumps(dict(structural), ensure_ascii=False),
                semantic_json=json.dumps(dict(semantic), ensure_ascii=False) if semantic is not None else None,
                model_profile=model_profile,
                reason=reason,
                retry_instruction=retry_instruction,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.segment_input_fingerprint = str(attempt["segment_input_fingerprint"])
            row.profile_version = QC_PROFILE_VERSION
            row.status = status
            row.quality_score = quality_score
            row.structural_json = json.dumps(dict(structural), ensure_ascii=False)
            row.semantic_json = json.dumps(dict(semantic), ensure_ascii=False) if semantic is not None else None
            row.model_profile = model_profile
            row.reason = reason
            row.retry_instruction = retry_instruction
            row.updated_at = now
        session.commit()
        session.refresh(row)
        return _serialize(row)


def get_generation_quality_check_v1(attempt_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.scalar(select(GenerationQualityCheck).where(
            GenerationQualityCheck.generation_attempt_id == attempt_id
        ))
        return _serialize(row) if row else None


def _condition_paths(attempt: Mapping[str, Any]) -> list[tuple[str, Path]]:
    request = attempt.get("request") if isinstance(attempt.get("request"), Mapping) else {}
    rows: list[tuple[str, Path]] = []
    for item in request.get("conditions") or []:
        if not isinstance(item, Mapping):
            continue
        path = _file_uri_path(str(item.get("uri") or ""))
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            continue
        rows.append((str(item.get("role") or item.get("type") or "condition"), path))
    return rows


def _semantic_assets(attempt: Mapping[str, Any], segment: Mapping[str, Any], structural: Mapping[str, Any]) -> list[tuple[str, Path]]:
    output = Path(str(attempt.get("output_path") or ""))
    duration_us = int(structural.get("actual_duration_us") or segment.get("target_duration_us") or 1)
    root = project_dir(str(attempt["project_id"])) / "target" / "h3" / "qc" / str(attempt["id"])
    labeled: list[tuple[str, Path]] = []
    for index, path in enumerate(_sample_video(output, duration_us, root, "generated"), start=1):
        labeled.append((f"GENERATED_{index}", path))

    conditions = _condition_paths(attempt)
    for role, path in conditions:
        if role.startswith("target_character:"):
            labeled.append((f"TARGET_CHARACTER_{role.split(':', 1)[1]}", path))
        elif role == "target_scene":
            labeled.append(("TARGET_SCENE", path))
        elif role == "first_frame":
            labeled.append(("CONTINUITY_FIRST_FRAME", path))
        elif role == "source_directing_reference":
            source_duration = max(2_000_000, int(segment.get("reference_clip_duration_us") or duration_us))
            for index, frame in enumerate(_sample_video(path, source_duration, root, "source"), start=1):
                labeled.append((f"SOURCE_{index}", frame))
    return labeled[:16]


def run_generation_attempt_qc_v1(attempt_id: str) -> dict[str, Any]:
    attempt = get_generation_attempt_v1(attempt_id)
    if attempt is None:
        raise LookupError("GenerationAttempt 不存在")
    if attempt.get("status") != "SUCCEEDED" or not attempt.get("output_path"):
        raise H3QualityError("只有 SUCCEEDED GenerationAttempt 才能执行 H3 QC")
    segment = _current_segment(str(attempt["project_id"]), str(attempt["generation_segment_id"]))
    structural = structural_h3_qc_v1(
        Path(str(attempt["output_path"])),
        expected_duration_us=int(segment["target_duration_us"]),
    )
    if str(segment.get("input_fingerprint") or "") != str(attempt["segment_input_fingerprint"]):
        return _persist_qc(
            attempt,
            status="STALE",
            structural=structural,
            semantic=None,
            quality_score=None,
            model_profile=None,
            reason="GenerationAttempt 已因上游事实变化失效",
            retry_instruction=None,
        )
    if not (structural["has_video"] and structural["decode_ok"] and structural["duration_ok"]):
        return _persist_qc(
            attempt,
            status="RETRY",
            structural=structural,
            semantic=None,
            quality_score=0.0,
            model_profile=None,
            reason=str(structural.get("error_message") or "H3 输出结构质检未通过"),
            retry_instruction="Generate a clean decodable video matching the exact planned duration; keep the same story action, target identities and camera plan.",
        )

    model_status = semantic_model_status()
    if not model_status.get("ready"):
        return _persist_qc(
            attempt,
            status="WAITING_MODEL",
            structural=structural,
            semantic=None,
            quality_score=None,
            model_profile=None,
            reason="本地 Qwen3-VL 未配置，H3 输出已通过结构检查但尚不能自动语义质检",
            retry_instruction=None,
        )

    try:
        assets = _semantic_assets(attempt, segment, structural)
        labels = [label for label, _path in assets]
        raw, model_profile = _request_semantic_qc(_semantic_prompt(segment, labels), assets)
        status, score, semantic, reason, retry_instruction = semantic_qc_policy_v1(raw, segment)
    except H3QualityError as exc:
        return _persist_qc(
            attempt,
            status="WAITING_MODEL",
            structural=structural,
            semantic=None,
            quality_score=None,
            model_profile=(
                f"openai-compatible:{model_status.get('model')}"
                if model_status.get("model")
                else None
            ),
            reason=f"Qwen3-VL H3 QC 暂不可用：{exc}",
            retry_instruction=None,
        )

    qc = _persist_qc(
        attempt,
        status=status,
        structural=structural,
        semantic=semantic,
        quality_score=score,
        model_profile=model_profile,
        reason=reason,
        retry_instruction=retry_instruction,
    )
    if status == "PASS":
        set_generation_selection_v1(
            attempt_id,
            selection_source="AUTO",
            quality_check_id=str(qc["id"]),
            quality_score=score,
        )
    return qc


def mark_stale_generation_quality_v1(project_id: str) -> int:
    current = _current_segments(project_id)
    changed = 0
    now = utcnow()
    with get_session() as session:
        rows = session.scalars(select(GenerationQualityCheck).where(
            GenerationQualityCheck.project_id == project_id,
            GenerationQualityCheck.status != "STALE",
        )).all()
        for row in rows:
            segment = current.get(row.generation_segment_id)
            attempt = session.get(GenerationAttempt, row.generation_attempt_id)
            valid = (
                segment is not None
                and attempt is not None
                and attempt.status == "SUCCEEDED"
                and str(segment.get("input_fingerprint") or "") == row.segment_input_fingerprint
                and attempt.segment_input_fingerprint == row.segment_input_fingerprint
            )
            if valid:
                continue
            row.status = "STALE"
            row.reason = "上游事实或 GenerationAttempt 状态已变化，旧 QC 不再参与当前选择"
            row.updated_at = now
            changed += 1
        if changed:
            session.commit()
    return changed


def get_generation_quality_summary_v1(project_id: str) -> dict[str, Any]:
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
    mark_stale_generation_quality_v1(project_id)
    selections = list_generation_selections_v1(project_id)
    with get_session() as session:
        rows = list(session.scalars(
            select(GenerationQualityCheck)
            .where(GenerationQualityCheck.project_id == project_id)
            .order_by(GenerationQualityCheck.created_at.asc())
        ).all())
    checks = [_serialize(row) for row in rows]
    return GenerationQualityProjectSummaryV1.model_validate({
        "schema_version": "generation-quality-summary-v1",
        "project_id": project_id,
        "check_count": len(checks),
        "pass_count": sum(item["status"] == "PASS" for item in checks),
        "retry_count": sum(item["status"] == "RETRY" for item in checks),
        "review_count": sum(item["status"] == "REVIEW" for item in checks),
        "waiting_model_count": sum(item["status"] == "WAITING_MODEL" for item in checks),
        "stale_count": sum(item["status"] == "STALE" for item in checks),
        "selected_count": len(selections),
        "checks": checks,
        "selections": selections,
    }).model_dump(mode="json")


def manual_select_generation_attempt_v1(attempt_id: str) -> dict[str, Any]:
    attempt = get_generation_attempt_v1(attempt_id)
    if attempt is None:
        raise LookupError("GenerationAttempt 不存在")
    if attempt.get("status") != "SUCCEEDED":
        raise H3QualityError("只能人工采用成功生成的视频版本")
    qc = get_generation_quality_check_v1(attempt_id) or run_generation_attempt_qc_v1(attempt_id)
    if qc["status"] == "STALE":
        raise H3QualityError("该版本已失效，不能人工采用")
    structural = qc["structural"]
    if not (structural["has_video"] and structural["decode_ok"] and structural["duration_ok"]):
        raise H3QualityError("该版本存在解码或时长硬错误，不能通过人工选择绕过")
    return set_generation_selection_v1(
        attempt_id,
        selection_source="MANUAL",
        quality_check_id=str(qc["id"]),
        quality_score=qc.get("quality_score"),
    )


def _current_attempts(project_id: str, segment_id: str, fingerprint: str) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.scalars(
            select(GenerationAttempt)
            .where(
                GenerationAttempt.project_id == project_id,
                GenerationAttempt.generation_segment_id == segment_id,
                GenerationAttempt.segment_input_fingerprint == fingerprint,
                GenerationAttempt.status != "STALE",
            )
            .order_by(GenerationAttempt.attempt_number.asc())
        ).all()
        return [get_generation_attempt_v1(row.id) for row in rows if row is not None]


def _publish_qc_review_issue(project_id: str, segment: Mapping[str, Any], reason: str) -> dict[str, Any]:
    segment_id = str(segment["id"])
    attempts = _current_attempts(project_id, segment_id, str(segment["input_fingerprint"]))
    checks = [
        qc
        for attempt in attempts
        if attempt is not None
        for qc in [get_generation_quality_check_v1(str(attempt["id"]))]
        if qc is not None and qc.get("status") != "STALE"
    ]
    return upsert_review_issue(
        project_id=project_id,
        episode_id=str(segment["episode_id"]),
        shot_id=segment.get("source_shot_id"),
        source_key=f"auto:h3-qc:{segment_id}",
        issue_type="H3_QC",
        severity="REVIEW",
        reason=reason,
        ai_suggestion={
            "best_quality_score": max((float(item["quality_score"]) for item in checks if item.get("quality_score") is not None), default=None),
            "last_retry_instruction": next((item.get("retry_instruction") for item in reversed(checks) if item.get("retry_instruction")), None),
        },
        editable_payload={
            "generation_segment_id": segment_id,
            "shot_ordinal": segment.get("shot_ordinal"),
            "shot_segment_index": segment.get("shot_segment_index"),
            "attempt_ids": [str(item["id"]) for item in attempts if item is not None],
            "quality_check_ids": [str(item["id"]) for item in checks],
        },
    )


def _max_auto_attempts() -> int:
    try:
        value = int(os.getenv("AI_DRAMA_H3_QC_MAX_ATTEMPTS", "3"))
    except ValueError:
        value = 3
    return max(1, min(5, value))


ProgressCallback = Callable[[int, int, str], None]


def run_generation_with_qc_v1(project_id: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
    character_refs = ensure_target_character_references_v1(project_id)
    scene_refs = ensure_target_scene_references_v1(project_id)
    plan = compile_generation_segments_v1(project_id)
    segments = [
        dict(segment)
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("status") == "READY"
    ]
    max_attempts = _max_auto_attempts()
    selected_now = 0
    reused_selected = 0
    generated_attempts = 0
    generation_failures: list[dict[str, str]] = []
    waiting: list[dict[str, str]] = []
    review: list[dict[str, str]] = []

    for index, segment in enumerate(segments, start=1):
        segment_id = str(segment["id"])
        fingerprint = str(segment["input_fingerprint"])
        if progress:
            progress(index, len(segments), f"H3 生成/QC {index}/{len(segments)} · Shot {segment.get('shot_ordinal')} · Segment {segment.get('shot_segment_index')}")
        if selected_generation_output_v1(project_id, segment_id) is not None:
            reused_selected += 1
            continue

        attempts = _current_attempts(project_id, segment_id, fingerprint)
        last_retry_instruction: str | None = None
        terminal_review_reason: str | None = None

        # Adopt pre-R9 successful attempts only after they pass the new QC boundary.
        for attempt in attempts:
            if attempt is None or attempt.get("status") != "SUCCEEDED":
                continue
            qc = get_generation_quality_check_v1(str(attempt["id"]))
            if qc is None or qc.get("status") == "WAITING_MODEL":
                qc = run_generation_attempt_qc_v1(str(attempt["id"]))
            if qc["status"] == "PASS":
                selected_now += 1
                break
            if qc["status"] == "WAITING_MODEL":
                waiting.append({"segment_id": segment_id, "reason": str(qc["reason"])})
                terminal_review_reason = "WAITING_MODEL"
                break
            if qc["status"] == "REVIEW":
                terminal_review_reason = str(qc["reason"])
                break
            if qc["status"] == "RETRY":
                last_retry_instruction = qc.get("retry_instruction")
        if selected_generation_output_v1(project_id, segment_id) is not None:
            continue
        if terminal_review_reason == "WAITING_MODEL":
            continue
        if terminal_review_reason:
            _publish_qc_review_issue(project_id, segment, terminal_review_reason)
            review.append({"segment_id": segment_id, "reason": terminal_review_reason})
            continue

        attempts_used = len(attempts)
        while attempts_used < max_attempts:
            try:
                attempt = execute_generation_segment_v1(
                    project_id,
                    segment_id,
                    retry_index=attempts_used,
                    retry_feedback=last_retry_instruction,
                    force_new=attempts_used > 0,
                )
                generated_attempts += 1
            except GenerationAttemptError as exc:
                attempts_used += 1
                generation_failures.append({"segment_id": segment_id, "error": str(exc)})
                continue

            attempts_used += 1
            if attempt.get("status") != "SUCCEEDED":
                generation_failures.append({"segment_id": segment_id, "error": str(attempt.get("error_message") or attempt.get("status"))})
                continue
            qc = run_generation_attempt_qc_v1(str(attempt["id"]))
            if qc["status"] == "PASS":
                selected_now += 1
                break
            if qc["status"] == "WAITING_MODEL":
                waiting.append({"segment_id": segment_id, "reason": str(qc["reason"])})
                break
            if qc["status"] == "REVIEW":
                terminal_review_reason = str(qc["reason"])
                break
            last_retry_instruction = qc.get("retry_instruction")

        if selected_generation_output_v1(project_id, segment_id) is not None:
            continue
        if terminal_review_reason:
            _publish_qc_review_issue(project_id, segment, terminal_review_reason)
            review.append({"segment_id": segment_id, "reason": terminal_review_reason})
            continue
        latest_qc = next(
            (
                get_generation_quality_check_v1(str(item["id"]))
                for item in reversed(_current_attempts(project_id, segment_id, fingerprint))
                if item is not None and item.get("status") == "SUCCEEDED"
            ),
            None,
        )
        if latest_qc and latest_qc.get("status") == "RETRY" and attempts_used >= max_attempts:
            reason = f"H3 已自动尝试 {attempts_used} 次仍未通过 QC：{latest_qc.get('reason')}"
            _publish_qc_review_issue(project_id, segment, reason)
            review.append({"segment_id": segment_id, "reason": reason})

    quality = get_generation_quality_summary_v1(project_id)
    return {
        "project_id": project_id,
        "generation_plan_status": plan.get("status"),
        "ready_segment_count": len(segments),
        "selected_now": selected_now,
        "reused_selected": reused_selected,
        "generated_attempts": generated_attempts,
        "generation_failures": generation_failures,
        "waiting": waiting,
        "review": review,
        "character_references": character_refs,
        "scene_references": scene_refs,
        "quality_summary": quality,
    }


def run_manual_qc_retry_v1(project_id: str, segment_id: str) -> dict[str, Any]:
    segment = _current_segment(project_id, segment_id)
    if segment.get("status") != "READY":
        raise H3QualityError("当前 GenerationSegment 尚不可重新生成")
    attempts = _current_attempts(project_id, segment_id, str(segment["input_fingerprint"]))
    latest_retry = next(
        (
            qc
            for attempt in reversed(attempts)
            if attempt is not None
            for qc in [get_generation_quality_check_v1(str(attempt["id"]))]
            if qc is not None and qc.get("retry_instruction")
        ),
        None,
    )
    attempt = execute_generation_segment_v1(
        project_id,
        segment_id,
        retry_index=len(attempts) + 1,
        retry_feedback=latest_retry.get("retry_instruction") if latest_retry else None,
        force_new=True,
    )
    qc = run_generation_attempt_qc_v1(str(attempt["id"])) if attempt.get("status") == "SUCCEEDED" else None
    if qc is not None and qc.get("status") in {"RETRY", "REVIEW"}:
        _publish_qc_review_issue(project_id, segment, str(qc.get("reason") or "手动重试后仍未通过 H3 QC"))
    return {"attempt": attempt, "quality_check": qc, "selection": list_generation_selections_v1(project_id)}


__all__ = [
    "GenerationQualityCheck",
    "H3QualityError",
    "QC_PROFILE_VERSION",
    "get_generation_quality_check_v1",
    "get_generation_quality_summary_v1",
    "manual_select_generation_attempt_v1",
    "mark_stale_generation_quality_v1",
    "run_generation_attempt_qc_v1",
    "run_generation_with_qc_v1",
    "run_manual_qc_retry_v1",
    "semantic_qc_policy_v1",
    "structural_h3_qc_v1",
]
