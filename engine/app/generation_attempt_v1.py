"""R8 real local H3 execution and GenerationAttempt persistence.

One GenerationAttempt records one immutable execution of one current GenerationSegment
context.  Provider-specific HTTP details remain behind VideoGenerationProvider.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.generation_segment_v1 import GenerationSegment, compile_generation_segments_v1, get_generation_segments_v1
from engine.app.h3_context_compiler_v1 import H3ContextCompilerError, compile_h3_context_v1
from engine.app.h3_context_contract_v1 import GenerationAttemptProjectSummaryV1, GenerationAttemptV1
from engine.app.h3_reference_assets_v1 import ensure_target_character_references_v1, ensure_target_scene_references_v1
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.studio_v2 import Base, Project, get_session, new_id, project_dir, utcnow
from engine.app.video_generation_provider_v1 import VideoGenerationProvider, VideoGenerationRequestV1


class GenerationAttemptError(RuntimeError):
    pass


class GenerationAttempt(Base):
    __tablename__ = "v2_generation_attempts"
    __table_args__ = (
        UniqueConstraint("generation_segment_id", "attempt_number", name="uq_v2_generation_attempt_segment_number"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    generation_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_segments.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PLANNED", index=True)
    external_job_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    provider_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _serialize(row: GenerationAttempt) -> dict[str, Any]:
    return GenerationAttemptV1.model_validate({
        "id": row.id,
        "project_id": row.project_id,
        "episode_id": row.episode_id,
        "generation_segment_id": row.generation_segment_id,
        "attempt_number": row.attempt_number,
        "segment_input_fingerprint": row.segment_input_fingerprint,
        "context_fingerprint": row.context_fingerprint,
        "provider": row.provider,
        "mode": row.mode,
        "status": row.status,
        "external_job_id": row.external_job_id,
        "provider_status": row.provider_status,
        "request": _json(row.request_json, {}),
        "output_path": row.output_path,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "updated_at": row.updated_at.isoformat(),
    }).model_dump(mode="json")


def _segment_map(project_id: str) -> dict[str, dict[str, Any]]:
    plan = get_generation_segments_v1(project_id)
    result: dict[str, dict[str, Any]] = {}
    for episode in plan.get("episodes") or []:
        for segment in episode.get("segments") or []:
            if isinstance(segment, Mapping) and segment.get("id"):
                result[str(segment["id"])] = dict(segment)
    return result


def _current_segment(project_id: str, segment_id: str) -> dict[str, Any]:
    segment = _segment_map(project_id).get(segment_id)
    if segment is None:
        raise LookupError("GenerationSegment 不存在或已经失效")
    return segment


def _mark_stale_attempts(project_id: str, current_segments: Mapping[str, Mapping[str, Any]]) -> int:
    changed = 0
    with get_session() as session:
        rows = session.scalars(select(GenerationAttempt).where(
            GenerationAttempt.project_id == project_id,
            GenerationAttempt.status.in_(["SUCCEEDED", "FAILED"]),
        )).all()
        now = utcnow()
        for row in rows:
            current = current_segments.get(row.generation_segment_id)
            if current is not None and str(current.get("input_fingerprint") or "") == row.segment_input_fingerprint:
                continue
            row.status = "STALE"
            row.completed_at = row.completed_at or now
            row.updated_at = now
            changed += 1
        if changed:
            session.commit()
    return changed


def _summary(project_id: str, rows: list[GenerationAttempt]) -> dict[str, Any]:
    payloads = [_serialize(row) for row in rows]
    return GenerationAttemptProjectSummaryV1.model_validate({
        "schema_version": "generation-attempt-summary-v1",
        "project_id": project_id,
        "attempt_count": len(payloads),
        "succeeded_count": sum(item["status"] == "SUCCEEDED" for item in payloads),
        "running_count": sum(item["status"] in {"PLANNED", "SUBMITTED", "RUNNING"} for item in payloads),
        "failed_count": sum(item["status"] == "FAILED" for item in payloads),
        "stale_count": sum(item["status"] == "STALE" for item in payloads),
        "attempts": payloads,
    }).model_dump(mode="json")


def list_generation_attempts_v1(project_id: str) -> dict[str, Any]:
    current_segments = _segment_map(project_id)
    _mark_stale_attempts(project_id, current_segments)
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        rows = list(session.scalars(
            select(GenerationAttempt)
            .where(GenerationAttempt.project_id == project_id)
            .order_by(GenerationAttempt.created_at.asc(), GenerationAttempt.attempt_number.asc())
        ).all())
        return _summary(project_id, rows)


def get_generation_attempt_v1(attempt_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(GenerationAttempt, attempt_id)
        return _serialize(row) if row else None


def latest_successful_generation_output_v1(project_id: str, segment_id: str) -> Path | None:
    try:
        current = _current_segment(project_id, segment_id)
    except (LookupError, Exception):
        return None
    fingerprint = str(current.get("input_fingerprint") or "")
    with get_session() as session:
        rows = session.scalars(
            select(GenerationAttempt)
            .where(
                GenerationAttempt.project_id == project_id,
                GenerationAttempt.generation_segment_id == segment_id,
                GenerationAttempt.segment_input_fingerprint == fingerprint,
                GenerationAttempt.status == "SUCCEEDED",
            )
            .order_by(GenerationAttempt.attempt_number.desc())
        ).all()
        for row in rows:
            path = Path(row.output_path) if row.output_path else None
            if path is not None and path.is_file() and path.stat().st_size > 0:
                return path
    return None


def _next_attempt_number(segment_id: str) -> int:
    with get_session() as session:
        value = session.scalar(
            select(func.max(GenerationAttempt.attempt_number)).where(
                GenerationAttempt.generation_segment_id == segment_id
            )
        )
    return int(value or 0) + 1


def _reuse_current_success(project_id: str, segment_id: str, context_fingerprint: str, segment_input_fingerprint: str) -> dict[str, Any] | None:
    with get_session() as session:
        rows = session.scalars(
            select(GenerationAttempt)
            .where(
                GenerationAttempt.project_id == project_id,
                GenerationAttempt.generation_segment_id == segment_id,
                GenerationAttempt.context_fingerprint == context_fingerprint,
                GenerationAttempt.segment_input_fingerprint == segment_input_fingerprint,
                GenerationAttempt.status == "SUCCEEDED",
            )
            .order_by(GenerationAttempt.attempt_number.desc())
        ).all()
        for row in rows:
            if row.output_path and Path(row.output_path).is_file() and Path(row.output_path).stat().st_size > 0:
                return _serialize(row)
    return None


def execute_generation_segment_v1(
    project_id: str,
    segment_id: str,
    *,
    provider: VideoGenerationProvider | None = None,
    poll_interval_seconds: float | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    segment = _current_segment(project_id, segment_id)
    if segment.get("status") != "READY":
        raise GenerationAttemptError(f"GenerationSegment 尚不可生成：{segment.get('reason')}")
    context = compile_h3_context_v1(project_id, segment_id)
    if context.get("status") != "READY" or not context.get("request"):
        raise GenerationAttemptError(str(context.get("reason") or "H3 Context 尚不可执行"))

    existing = _reuse_current_success(
        project_id,
        segment_id,
        str(context["context_fingerprint"]),
        str(segment["input_fingerprint"]),
    )
    if existing is not None:
        return existing

    request = VideoGenerationRequestV1.model_validate(context["request"])
    generation_provider = provider or get_video_generation_provider_v1(request.provider)
    attempt_number = _next_attempt_number(segment_id)
    now = utcnow()
    with get_session() as session:
        row = GenerationAttempt(
            id=new_id("GENATTEMPT"),
            project_id=project_id,
            episode_id=str(segment["episode_id"]),
            generation_segment_id=segment_id,
            attempt_number=attempt_number,
            segment_input_fingerprint=str(segment["input_fingerprint"]),
            context_fingerprint=str(context["context_fingerprint"]),
            provider=request.provider,
            mode=request.mode,
            status="PLANNED",
            request_json=json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        attempt_id = row.id

    try:
        submission = generation_provider.submit(request)
        with get_session() as session:
            row = session.get(GenerationAttempt, attempt_id)
            if row is None:
                raise GenerationAttemptError("GenerationAttempt 提交后记录丢失")
            row.external_job_id = submission.external_job_id
            row.provider_status = submission.provider_status
            row.status = "SUBMITTED"
            row.submitted_at = utcnow()
            row.updated_at = utcnow()
            session.commit()

        interval = max(0.2, float(poll_interval_seconds if poll_interval_seconds is not None else os.getenv("AI_DRAMA_H3_POLL_INTERVAL", "3")))
        timeout = max(30.0, float(timeout_seconds if timeout_seconds is not None else os.getenv("AI_DRAMA_H3_GENERATION_TIMEOUT", "3600")))
        deadline = time.monotonic() + timeout
        final_provider_status: str | None = submission.provider_status
        while True:
            job = generation_provider.get_status(mode=request.mode, external_job_id=submission.external_job_id)
            final_provider_status = job.provider_status
            if job.terminal:
                if job.failed or not job.succeeded:
                    raise GenerationAttemptError(job.error_message or f"H3 任务失败：{job.provider_status}")
                break
            with get_session() as session:
                row = session.get(GenerationAttempt, attempt_id)
                if row is not None:
                    row.status = "RUNNING"
                    row.provider_status = job.provider_status
                    row.updated_at = utcnow()
                    session.commit()
            if time.monotonic() >= deadline:
                raise GenerationAttemptError("H3 生成任务等待超时")
            time.sleep(interval)

        output = (
            project_dir(project_id)
            / "target" / "h3" / "outputs"
            / str(segment["episode_id"])
            / segment_id
            / f"attempt-{attempt_number:03d}.mp4"
        )
        generation_provider.download(
            mode=request.mode,
            external_job_id=submission.external_job_id,
            destination=output,
        )
        if not output.is_file() or output.stat().st_size <= 0:
            raise GenerationAttemptError("H3 输出文件为空")

        # Never publish an output as current success after authoritative upstream data changed
        # while the local H3 job was running.
        try:
            after = _current_segment(project_id, segment_id)
            still_current = str(after.get("input_fingerprint") or "") == str(segment["input_fingerprint"])
        except Exception:
            still_current = False
        completed = utcnow()
        with get_session() as session:
            row = session.get(GenerationAttempt, attempt_id)
            if row is None:
                raise GenerationAttemptError("GenerationAttempt 下载后记录丢失")
            row.provider_status = final_provider_status
            row.output_path = str(output)
            row.status = "SUCCEEDED" if still_current else "STALE"
            row.error_message = None if still_current else "上游事实在 H3 生成期间发生变化，输出保留但不再作为当前结果"
            row.completed_at = completed
            row.updated_at = completed
            session.commit(); session.refresh(row)
            return _serialize(row)
    except Exception as exc:
        completed = utcnow()
        with get_session() as session:
            row = session.get(GenerationAttempt, attempt_id)
            if row is not None:
                row.status = "FAILED"
                row.error_message = str(exc)[:4000]
                row.completed_at = completed
                row.updated_at = completed
                session.commit(); session.refresh(row)
                result = _serialize(row)
            else:
                result = None
        if isinstance(exc, GenerationAttemptError):
            raise
        raise GenerationAttemptError(str(exc)) from exc


ProgressCallback = Callable[[int, int, str], None]


def run_ready_generation_segments_v1(
    project_id: str,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    # References are themselves automatic H3 work. Failure does not create a fake human content
    # issue; affected contexts remain WAITING_REFERENCE and can resume when runtime/resources work.
    character_refs = ensure_target_character_references_v1(project_id)
    scene_refs = ensure_target_scene_references_v1(project_id)
    plan = compile_generation_segments_v1(project_id)
    segments = [
        dict(segment)
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping)
    ]
    ready = [item for item in segments if item.get("status") == "READY"]
    succeeded = 0
    reused = 0
    failed: list[dict[str, str]] = []
    waiting: list[dict[str, str]] = []
    total = len(ready)
    for index, segment in enumerate(ready, start=1):
        segment_id = str(segment["id"])
        if progress:
            progress(index, total, f"正在生成 {index}/{total} · Shot {segment.get('shot_ordinal')} · Segment {segment.get('shot_segment_index')}")
        before = latest_successful_generation_output_v1(project_id, segment_id)
        if before is not None:
            reused += 1
            continue
        try:
            attempt = execute_generation_segment_v1(project_id, segment_id)
            if attempt.get("status") == "SUCCEEDED":
                succeeded += 1
            elif attempt.get("status") == "STALE":
                waiting.append({"segment_id": segment_id, "reason": "生成完成时上游已变化，需要重新编译"})
        except (GenerationAttemptError, H3ContextCompilerError) as exc:
            message = str(exc)
            if "尚未生成当前版本参考资产" in message or "需要上一 GenerationSegment" in message:
                waiting.append({"segment_id": segment_id, "reason": message})
            else:
                failed.append({"segment_id": segment_id, "error": message})

    summary = list_generation_attempts_v1(project_id)
    return {
        "project_id": project_id,
        "generation_plan_status": plan.get("status"),
        "segment_count": len(segments),
        "ready_segment_count": len(ready),
        "succeeded_now": succeeded,
        "reused_success": reused,
        "failed": failed,
        "waiting": waiting,
        "character_references": character_refs,
        "scene_references": scene_refs,
        "attempt_summary": summary,
    }


__all__ = [
    "GenerationAttempt",
    "GenerationAttemptError",
    "execute_generation_segment_v1",
    "get_generation_attempt_v1",
    "latest_successful_generation_output_v1",
    "list_generation_attempts_v1",
    "run_ready_generation_segments_v1",
]
