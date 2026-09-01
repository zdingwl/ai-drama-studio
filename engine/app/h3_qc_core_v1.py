"""R9 H3 QC core: structural checks, Qwen3-VL semantic checks and persisted QC results."""
from __future__ import annotations

import base64
from datetime import datetime
import json
import mimetypes
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.asset_semantics_v3 import semantic_model_status
from engine.app.generation_attempt_v1 import GenerationAttempt, get_generation_attempt_v1
from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.generation_selection_v1 import list_generation_selections_v1, set_generation_selection_v1
from engine.app.h3_qc_contract_v1 import (
    GenerationQualityCheckV1,
    GenerationQualityProjectSummaryV1,
    GenerationSemanticQCV1,
    GenerationStructuralQCV1,
)
from engine.app.review_issue_v1 import upsert_review_issue
from engine.app.studio_v2 import Base, Project, get_session, new_id, project_dir, utcnow


QC_PROFILE_VERSION = "H3_QC_V1"
VISUAL_INTEGRITY_MIN = 0.80
CHARACTER_CONSISTENCY_MIN = 0.72
SCENE_CONSISTENCY_MIN = 0.72
ACTION_CAMERA_MIN = 0.68
CONTINUITY_MIN = 0.72
SEMANTIC_CONFIDENCE_MIN = 0.55


class H3QualityError(RuntimeError):
    pass


class GenerationQualityCheck(Base):
    __tablename__ = "v2_generation_quality_checks"
    __table_args__ = (UniqueConstraint("generation_attempt_id", name="uq_v2_generation_quality_attempt"),)

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


def current_generation_segment_v1(project_id: str, segment_id: str) -> dict[str, Any]:
    segment = _current_segments(project_id).get(segment_id)
    if segment is None:
        raise LookupError("GenerationSegment 不存在或已经失效")
    return segment


def _run(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
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
            a, b = raw.split("/", 1)
            denominator = float(b)
            return float(a) / denominator if denominator else None
        return float(raw)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def structural_h3_qc_v1(path: Path, *, expected_duration_us: int) -> dict[str, Any]:
    expected = max(1, int(expected_duration_us))
    payload: dict[str, Any] = {
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
        payload["error_message"] = "H3 输出文件不存在或为空"
        return GenerationStructuralQCV1.model_validate(payload).model_dump(mode="json")
    try:
        probe = _run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of", "json", str(path),
        ], timeout_seconds=180)
        body = json.loads(probe.stdout or "{}")
        streams = body.get("streams") or []
        video = next((item for item in streams if isinstance(item, Mapping) and item.get("codec_type") == "video"), None)
        duration_raw = (body.get("format") or {}).get("duration") if isinstance(body.get("format"), Mapping) else None
        actual = int(round(float(duration_raw) * 1_000_000)) if duration_raw not in (None, "", "N/A") else None
        fps = _parse_fps(video.get("avg_frame_rate")) if isinstance(video, Mapping) else None
        tolerance = max(180_000, int(round(3_000_000 / fps))) if fps and fps > 0 else 250_000
        delta = actual - expected if actual is not None else None
        payload.update({
            "actual_duration_us": actual,
            "duration_delta_us": delta,
            "duration_tolerance_us": tolerance,
            "duration_ok": actual is not None and abs(delta or 0) <= tolerance,
            "has_video": video is not None,
            "width": (int(video.get("width") or 0) or None) if isinstance(video, Mapping) else None,
            "height": (int(video.get("height") or 0) or None) if isinstance(video, Mapping) else None,
            "fps": fps,
        })
        if video is None:
            payload["error_message"] = "H3 输出没有视频流"
        else:
            _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], timeout_seconds=1200)
            payload["decode_ok"] = True
            if not payload["duration_ok"]:
                payload["error_message"] = f"H3 输出时长偏差 {delta or 0}us，超过允许误差 {tolerance}us"
    except (H3QualityError, ValueError, TypeError, json.JSONDecodeError) as exc:
        payload["error_message"] = str(exc)[:3500]
    return GenerationStructuralQCV1.model_validate(payload).model_dump(mode="json")


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
    return [
        _extract_frame(video, seconds * ratio, root / f"{prefix}-{index}.jpg")
        for index, ratio in enumerate((0.15, 0.50, 0.85), start=1)
    ]


def _score(value: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise H3QualityError("Qwen3-VL QC 没有返回 JSON")
    try:
        value = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        raise H3QualityError("Qwen3-VL QC JSON 无法解析") from exc
    if not isinstance(value, dict):
        raise H3QualityError("Qwen3-VL QC 返回的不是 JSON object")
    return value


def semantic_qc_policy_v1(raw: Mapping[str, Any], segment: Mapping[str, Any]) -> tuple[str, float | None, dict[str, Any], str, str | None]:
    semantic = GenerationSemanticQCV1.model_validate({
        "visual_integrity": _score(raw.get("visual_integrity")),
        "target_character_consistency": _score(raw.get("target_character_consistency")),
        "scene_consistency": _score(raw.get("scene_consistency")),
        "action_camera_consistency": _score(raw.get("action_camera_consistency")),
        "continuity_consistency": _score(raw.get("continuity_consistency")),
        "confidence": _score(raw.get("confidence")),
        "source_actor_leak": _as_bool(raw.get("source_actor_leak")),
        "obvious_visual_artifact": _as_bool(raw.get("obvious_visual_artifact")),
        "reasons": [str(item).strip() for item in (raw.get("reasons") or []) if str(item).strip()][:12],
        "retry_instruction": str(raw.get("retry_instruction") or "").strip()[:4000] or None,
        "raw": dict(raw),
    }).model_dump(mode="json")
    required: list[tuple[str, float]] = [("visual_integrity", VISUAL_INTEGRITY_MIN)]
    if segment.get("target_characters"):
        required.append(("target_character_consistency", CHARACTER_CONSISTENCY_MIN))
    if isinstance(segment.get("target_scene"), Mapping):
        required.append(("scene_consistency", SCENE_CONSISTENCY_MIN))
    if segment.get("generation_mode") == "REF2VA":
        required.append(("action_camera_consistency", ACTION_CAMERA_MIN))
    if segment.get("continuity_from_segment_id"):
        required.append(("continuity_consistency", CONTINUITY_MIN))
    missing = [name for name, _ in required if semantic.get(name) is None]
    if missing or semantic.get("confidence") is None:
        raise H3QualityError("Qwen3-VL H3 QC 缺少必要评分")
    values = [float(semantic[name]) for name, _ in required]
    quality = sum(values) / len(values)
    retry = semantic.get("retry_instruction")
    if semantic["source_actor_leak"]:
        return "RETRY", quality, semantic, "检测到原演员身份泄漏到目标视频", retry or "Replace every visible source actor with the target character identity references while preserving only source blocking and camera motion."
    if semantic["obvious_visual_artifact"]:
        return "RETRY", quality, semantic, "检测到明显 H3 生成崩坏或人物结构异常", retry or "Remove visible generation artifacts, identity morphing and anatomy errors while preserving the planned shot."
    if float(semantic["confidence"]) < SEMANTIC_CONFIDENCE_MIN:
        return "REVIEW", quality, semantic, "自动视觉质检置信度不足，需要人工查看已有版本", retry
    failed = [(name, float(semantic[name]), threshold) for name, threshold in required if float(semantic[name]) < threshold]
    if not failed:
        return "PASS", quality, semantic, "H3 结构与语义质检通过", None
    detail = "；".join(f"{name}={value:.2f}<{threshold:.2f}" for name, value, threshold in failed)
    return "RETRY", quality, semantic, "H3 质量未达到自动通过阈值：" + detail, retry


def _attempt_condition_paths(attempt: Mapping[str, Any]) -> list[tuple[str, Path]]:
    request = attempt.get("request") if isinstance(attempt.get("request"), Mapping) else {}
    result: list[tuple[str, Path]] = []
    for item in request.get("conditions") or []:
        if not isinstance(item, Mapping):
            continue
        path = _file_uri_path(str(item.get("uri") or ""))
        if path is not None and path.is_file() and path.stat().st_size > 0:
            result.append((str(item.get("role") or item.get("type") or "condition"), path))
    return result


def _semantic_assets(attempt: Mapping[str, Any], segment: Mapping[str, Any], structural: Mapping[str, Any]) -> list[tuple[str, Path]]:
    output = Path(str(attempt["output_path"]))
    duration_us = int(structural.get("actual_duration_us") or segment.get("target_duration_us") or 1)
    root = project_dir(str(attempt["project_id"])) / "target" / "h3" / "qc" / str(attempt["id"])
    labeled = [(f"GENERATED_{i}", path) for i, path in enumerate(_sample_video(output, duration_us, root, "generated"), start=1)]
    for role, path in _attempt_condition_paths(attempt):
        if role.startswith("target_character:"):
            labeled.append(("TARGET_CHARACTER_" + role.split(":", 1)[1], path))
        elif role == "target_scene":
            labeled.append(("TARGET_SCENE", path))
        elif role == "first_frame":
            labeled.append(("CONTINUITY_FIRST_FRAME", path))
        elif role == "source_directing_reference":
            source_duration = max(2_000_000, int(segment.get("reference_clip_duration_us") or duration_us))
            labeled.extend((f"SOURCE_{i}", frame) for i, frame in enumerate(_sample_video(path, source_duration, root, "source"), start=1))
    return labeled[:16]


def _semantic_prompt(segment: Mapping[str, Any], labels: list[str]) -> str:
    facts = {
        "generation_mode": segment.get("generation_mode"),
        "visual_description": segment.get("visual_description"),
        "performance": segment.get("performance") or [],
        "cinematography": segment.get("cinematography") or {},
        "target_characters": [
            {"target_name": item.get("target_name"), "appearance_profile": item.get("appearance_profile")}
            for item in segment.get("target_characters") or [] if isinstance(item, Mapping)
        ],
        "target_scene": segment.get("target_scene"),
        "labels": labels,
    }
    return (
        "你是短剧出海重拍的 H3 成片质检器。只返回 JSON。GENERATED_* 是待质检新视频；TARGET_CHARACTER_* 是目标演员身份参考；"
        "TARGET_SCENE 是目标场景；SOURCE_* 只用于比较动作、走位、构图和镜头，绝不能把 SOURCE 原演员当成目标人物；"
        "CONTINUITY_FIRST_FRAME 是上一条已通过 QC 的连续首帧。不要评价最终口型同步。"
        "检查明显畸形/融脸/额外肢体/变脸/人物消失、目标人物一致性、场景一致性、Ref2VA 动作镜头一致性和连续首帧承接。"
        "分数 0..1，信息不足降低 confidence。严格返回："
        "{\"visual_integrity\":0.0,\"target_character_consistency\":null,\"scene_consistency\":null,"
        "\"action_camera_consistency\":null,\"continuity_consistency\":null,\"confidence\":0.0,"
        "\"source_actor_leak\":false,\"obvious_visual_artifact\":false,\"reasons\":[\"\"],"
        "\"retry_instruction\":\"specific English correction for the next H3 attempt\"}."
        f"业务事实：{json.dumps(facts, ensure_ascii=False)}"
    )


def _request_semantic_qc(prompt: str, images: list[tuple[str, Path]]) -> tuple[dict[str, Any], str]:
    status = semantic_model_status()
    if not status.get("ready"):
        raise H3QualityError("Qwen3-VL 本地服务未配置")
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for label, path in images:
        content += [{"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": _image_data_url(path)}}]
    payload = {"model": str(status["model"]), "temperature": 0.0, "messages": [{"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {os.getenv('AI_DRAMA_VLM_API_KEY', 'EMPTY').strip() or 'EMPTY'}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=240.0) as client:
            response = client.post(f"{status['base_url']}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        raw = body["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise H3QualityError(f"Qwen3-VL H3 QC 请求失败：{exc}") from exc
    if isinstance(raw, list):
        raw = "".join(str(item.get("text") or "") for item in raw if isinstance(item, dict))
    return _extract_json(str(raw)), f"openai-compatible:{status['model']}"


def _persist_qc(attempt: Mapping[str, Any], *, status: str, structural: Mapping[str, Any], semantic: Mapping[str, Any] | None, quality_score: float | None, model_profile: str | None, reason: str, retry_instruction: str | None) -> dict[str, Any]:
    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(GenerationQualityCheck).where(GenerationQualityCheck.generation_attempt_id == str(attempt["id"])))
        if row is None:
            row = GenerationQualityCheck(
                id=new_id("H3QC"), project_id=str(attempt["project_id"]), episode_id=str(attempt["episode_id"]),
                generation_segment_id=str(attempt["generation_segment_id"]), generation_attempt_id=str(attempt["id"]),
                segment_input_fingerprint=str(attempt["segment_input_fingerprint"]), profile_version=QC_PROFILE_VERSION,
                status=status, quality_score=quality_score, structural_json=json.dumps(dict(structural), ensure_ascii=False),
                semantic_json=json.dumps(dict(semantic), ensure_ascii=False) if semantic is not None else None,
                model_profile=model_profile, reason=reason, retry_instruction=retry_instruction, created_at=now, updated_at=now,
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
        session.commit(); session.refresh(row)
        return _serialize(row)


def get_generation_quality_check_v1(attempt_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.scalar(select(GenerationQualityCheck).where(GenerationQualityCheck.generation_attempt_id == attempt_id))
        return _serialize(row) if row else None


def run_generation_attempt_qc_v1(attempt_id: str) -> dict[str, Any]:
    attempt = get_generation_attempt_v1(attempt_id)
    if attempt is None:
        raise LookupError("GenerationAttempt 不存在")
    if attempt.get("status") != "SUCCEEDED" or not attempt.get("output_path"):
        raise H3QualityError("只有 SUCCEEDED GenerationAttempt 才能执行 H3 QC")
    segment = current_generation_segment_v1(str(attempt["project_id"]), str(attempt["generation_segment_id"]))
    structural = structural_h3_qc_v1(Path(str(attempt["output_path"])), expected_duration_us=int(segment["target_duration_us"]))
    if str(segment.get("input_fingerprint") or "") != str(attempt["segment_input_fingerprint"]):
        return _persist_qc(attempt, status="STALE", structural=structural, semantic=None, quality_score=None, model_profile=None, reason="GenerationAttempt 已因上游事实变化失效", retry_instruction=None)
    if not (structural["has_video"] and structural["decode_ok"] and structural["duration_ok"]):
        return _persist_qc(attempt, status="RETRY", structural=structural, semantic=None, quality_score=0.0, model_profile=None, reason=str(structural.get("error_message") or "H3 输出结构质检未通过"), retry_instruction="Generate a clean decodable video matching the exact planned duration while preserving target identities and the planned shot.")
    model_status = semantic_model_status()
    if not model_status.get("ready"):
        return _persist_qc(attempt, status="WAITING_MODEL", structural=structural, semantic=None, quality_score=None, model_profile=None, reason="本地 Qwen3-VL 未配置，结构检查已通过但尚不能自动语义质检", retry_instruction=None)
    try:
        images = _semantic_assets(attempt, segment, structural)
        raw, model_profile = _request_semantic_qc(_semantic_prompt(segment, [label for label, _ in images]), images)
        status, quality, semantic, reason, retry = semantic_qc_policy_v1(raw, segment)
    except H3QualityError as exc:
        return _persist_qc(attempt, status="WAITING_MODEL", structural=structural, semantic=None, quality_score=None, model_profile=f"openai-compatible:{model_status.get('model')}" if model_status.get("model") else None, reason=f"Qwen3-VL H3 QC 暂不可用：{exc}", retry_instruction=None)
    qc = _persist_qc(attempt, status=status, structural=structural, semantic=semantic, quality_score=quality, model_profile=model_profile, reason=reason, retry_instruction=retry)
    if status == "PASS":
        set_generation_selection_v1(attempt_id, selection_source="AUTO", quality_check_id=str(qc["id"]), quality_score=quality)
    return qc


def mark_stale_generation_quality_v1(project_id: str) -> int:
    current = _current_segments(project_id)
    changed = 0
    now = utcnow()
    with get_session() as session:
        rows = session.scalars(select(GenerationQualityCheck).where(GenerationQualityCheck.project_id == project_id, GenerationQualityCheck.status != "STALE")).all()
        for row in rows:
            segment = current.get(row.generation_segment_id)
            attempt = session.get(GenerationAttempt, row.generation_attempt_id)
            valid = segment is not None and attempt is not None and attempt.status == "SUCCEEDED" and str(segment.get("input_fingerprint") or "") == row.segment_input_fingerprint and attempt.segment_input_fingerprint == row.segment_input_fingerprint
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
        rows = list(session.scalars(select(GenerationQualityCheck).where(GenerationQualityCheck.project_id == project_id).order_by(GenerationQualityCheck.created_at)).all())
    checks = [_serialize(row) for row in rows]
    return GenerationQualityProjectSummaryV1.model_validate({
        "schema_version": "generation-quality-summary-v1", "project_id": project_id,
        "check_count": len(checks), "pass_count": sum(item["status"] == "PASS" for item in checks),
        "retry_count": sum(item["status"] == "RETRY" for item in checks), "review_count": sum(item["status"] == "REVIEW" for item in checks),
        "waiting_model_count": sum(item["status"] == "WAITING_MODEL" for item in checks), "stale_count": sum(item["status"] == "STALE" for item in checks),
        "selected_count": len(selections), "checks": checks, "selections": selections,
    }).model_dump(mode="json")


def manual_select_generation_attempt_v1(attempt_id: str) -> dict[str, Any]:
    attempt = get_generation_attempt_v1(attempt_id)
    if attempt is None:
        raise LookupError("GenerationAttempt 不存在")
    if attempt.get("status") != "SUCCEEDED":
        raise H3QualityError("只能人工采用成功生成的视频版本")
    qc = get_generation_quality_check_v1(attempt_id) or run_generation_attempt_qc_v1(attempt_id)
    structural = qc["structural"]
    if qc["status"] == "STALE" or not (structural["has_video"] and structural["decode_ok"] and structural["duration_ok"]):
        raise H3QualityError("该版本存在失效、解码或时长硬错误，不能人工绕过")
    return set_generation_selection_v1(attempt_id, selection_source="MANUAL", quality_check_id=str(qc["id"]), quality_score=qc.get("quality_score"))


def current_attempts_for_segment_v1(project_id: str, segment_id: str, fingerprint: str) -> list[dict[str, Any]]:
    with get_session() as session:
        ids = [row.id for row in session.scalars(select(GenerationAttempt).where(
            GenerationAttempt.project_id == project_id,
            GenerationAttempt.generation_segment_id == segment_id,
            GenerationAttempt.segment_input_fingerprint == fingerprint,
            GenerationAttempt.status != "STALE",
        ).order_by(GenerationAttempt.attempt_number)).all()]
    return [item for item in (get_generation_attempt_v1(attempt_id) for attempt_id in ids) if item is not None]


def publish_h3_qc_review_issue_v1(project_id: str, segment: Mapping[str, Any], reason: str) -> dict[str, Any]:
    attempts = current_attempts_for_segment_v1(project_id, str(segment["id"]), str(segment["input_fingerprint"]))
    checks = [qc for attempt in attempts for qc in [get_generation_quality_check_v1(str(attempt["id"]))] if qc is not None and qc.get("status") != "STALE"]
    return upsert_review_issue(
        project_id=project_id,
        episode_id=str(segment["episode_id"]),
        shot_id=segment.get("source_shot_id"),
        source_key=f"auto:h3-qc:{segment['id']}",
        issue_type="H3_QC",
        severity="REVIEW",
        reason=reason,
        ai_suggestion={
            "best_quality_score": max((float(item["quality_score"]) for item in checks if item.get("quality_score") is not None), default=None),
            "last_retry_instruction": next((item.get("retry_instruction") for item in reversed(checks) if item.get("retry_instruction")), None),
        },
        editable_payload={
            "generation_segment_id": segment["id"],
            "shot_ordinal": segment.get("shot_ordinal"),
            "shot_segment_index": segment.get("shot_segment_index"),
            "attempt_ids": [item["id"] for item in attempts],
            "quality_check_ids": [item["id"] for item in checks],
        },
    )


__all__ = [
    "GenerationQualityCheck", "H3QualityError", "QC_PROFILE_VERSION",
    "current_attempts_for_segment_v1", "current_generation_segment_v1",
    "get_generation_quality_check_v1", "get_generation_quality_summary_v1",
    "manual_select_generation_attempt_v1", "mark_stale_generation_quality_v1",
    "publish_h3_qc_review_issue_v1", "run_generation_attempt_qc_v1",
    "semantic_qc_policy_v1", "structural_h3_qc_v1",
]
