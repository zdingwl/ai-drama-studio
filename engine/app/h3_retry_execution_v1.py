"""R9 immutable H3 retry executor.

R8 owns the normal first-attempt execution. R9 needs a distinct execution path because an H3 file
can be technically SUCCEEDED but rejected by QC. A retry must therefore use a different seed and
QC correction prompt, and FL2VA continuity must use the QC-selected previous output rather than
merely the latest technically successful attempt.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

from sqlalchemy import func, select

from engine.app.generation_attempt_v1 import (
    GenerationAttempt,
    GenerationAttemptError,
    _finalize_downloaded_output,
    get_generation_attempt_v1,
)
from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.generation_selection_v1 import selected_generation_output_v1
from engine.app.h3_context_compiler_v1 import compile_h3_context_v1
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.studio_v2 import get_session, new_id, project_dir, utcnow
from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1


class H3RetryExecutionError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current_segment(project_id: str, segment_id: str) -> dict[str, Any]:
    plan = get_generation_segments_v1(project_id)
    for episode in plan.get("episodes") or []:
        for segment in episode.get("segments") or []:
            if isinstance(segment, Mapping) and segment.get("id") == segment_id:
                return dict(segment)
    raise LookupError("GenerationSegment 不存在或已经失效")


def _next_attempt_number(segment_id: str) -> int:
    with get_session() as session:
        value = session.scalar(select(func.max(GenerationAttempt.attempt_number)).where(
            GenerationAttempt.generation_segment_id == segment_id
        ))
    return int(value or 0) + 1


def _extract_last_frame(video: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-sseof", "-0.080", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(output)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise H3RetryExecutionError("找不到 ffmpeg，无法准备 FL2VA 连续首帧") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise H3RetryExecutionError(f"FL2VA 连续首帧提取失败：{detail}") from exc
    if not output.is_file() or output.stat().st_size <= 0:
        raise H3RetryExecutionError("FL2VA 连续首帧为空")
    return output


def _retry_request(
    project_id: str,
    segment: Mapping[str, Any],
    *,
    retry_index: int,
    retry_feedback: str | None,
) -> tuple[VideoGenerationRequestV1, str]:
    segment_id = str(segment["id"])
    context = compile_h3_context_v1(project_id, segment_id)
    if context.get("status") != "READY" or not context.get("request"):
        raise H3RetryExecutionError(str(context.get("reason") or "H3 Context 尚不可执行"))
    request_payload = dict(context["request"])
    conditions = [dict(item) for item in request_payload.get("conditions") or [] if isinstance(item, Mapping)]

    previous_segment_id = str(segment.get("continuity_from_segment_id") or "")
    if previous_segment_id:
        selected = selected_generation_output_v1(project_id, previous_segment_id)
        if selected is None:
            raise H3RetryExecutionError("FL2VA 连续段必须等待上一 GenerationSegment 通过 QC 并成为 Selected Output")
        workspace = Path(str(context["workspace_dir"])) / "r9-retry"
        first_frame = _extract_last_frame(selected, workspace / f"selected-continuity-{max(0, retry_index)}.jpg")
        replaced = False
        for item in conditions:
            if item.get("role") == "first_frame":
                item["uri"] = first_frame.resolve().as_uri()
                item["frame_index"] = 0
                replaced = True
        if not replaced:
            conditions.insert(0, {
                "type": "image",
                "uri": first_frame.resolve().as_uri(),
                "role": "first_frame",
                "frame_index": 0,
            })

    prompt = str(request_payload.get("prompt") or "").strip()
    feedback = str(retry_feedback or "").strip()
    if feedback:
        prompt += (
            "\n\nqc_retry_correction:\n"
            "The previous generated attempt failed automatic QC. Correct only the following defects while preserving the planned plot event, target timing, target identities and camera intent:\n"
            + feedback[:4000]
        )
    base_seed = int(request_payload.get("seed") or 0)
    seed = (base_seed + max(1, int(retry_index)) * 104_729) % 2_147_483_647
    request_payload["prompt"] = prompt
    request_payload["conditions"] = conditions
    request_payload["seed"] = seed
    request = VideoGenerationRequestV1.model_validate(request_payload)
    context_fingerprint = _digest({
        "r9_profile": "H3_QC_RETRY_V1",
        "segment_input_fingerprint": segment["input_fingerprint"],
        "retry_index": int(retry_index),
        "request": request.model_dump(mode="json", exclude_none=True),
    })
    return request, context_fingerprint


def execute_generation_retry_v1(
    project_id: str,
    segment_id: str,
    *,
    retry_index: int,
    retry_feedback: str | None = None,
) -> dict[str, Any]:
    segment = _current_segment(project_id, segment_id)
    if segment.get("status") != "READY":
        raise H3RetryExecutionError(f"GenerationSegment 尚不可生成：{segment.get('reason')}")
    request, context_fingerprint = _retry_request(
        project_id,
        segment,
        retry_index=retry_index,
        retry_feedback=retry_feedback,
    )
    provider = get_video_generation_provider_v1(request.provider)
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
            context_fingerprint=context_fingerprint,
            provider=request.provider,
            mode=request.mode,
            status="PLANNED",
            request_json=json.dumps(request.model_dump(mode="json", exclude_none=True), ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        attempt_id = row.id

    try:
        submission = provider.submit(request)
        with get_session() as session:
            row = session.get(GenerationAttempt, attempt_id)
            if row is None:
                raise H3RetryExecutionError("GenerationAttempt 提交后记录丢失")
            row.external_job_id = submission.external_job_id
            row.provider_status = submission.provider_status
            row.status = "SUBMITTED"
            row.submitted_at = utcnow()
            row.updated_at = utcnow()
            session.commit()

        interval = max(0.2, float(os.getenv("AI_DRAMA_H3_POLL_INTERVAL", "3")))
        timeout = max(30.0, float(os.getenv("AI_DRAMA_H3_GENERATION_TIMEOUT", "3600")))
        deadline = time.monotonic() + timeout
        final_provider_status = submission.provider_status
        while True:
            job = provider.get_status(mode=request.mode, external_job_id=submission.external_job_id)
            final_provider_status = job.provider_status
            if job.terminal:
                if job.failed or not job.succeeded:
                    raise H3RetryExecutionError(job.error_message or f"H3 重试失败：{job.provider_status}")
                break
            with get_session() as session:
                row = session.get(GenerationAttempt, attempt_id)
                if row is not None:
                    row.status = "RUNNING"
                    row.provider_status = job.provider_status
                    row.updated_at = utcnow()
                    session.commit()
            if time.monotonic() >= deadline:
                raise H3RetryExecutionError("H3 重试等待超时")
            time.sleep(interval)

        attempt_dir = project_dir(project_id) / "target" / "h3" / "outputs" / str(segment["episode_id"]) / segment_id
        raw_output = attempt_dir / f"attempt-{attempt_number:03d}.h3.mp4"
        output = attempt_dir / f"attempt-{attempt_number:03d}.mp4"
        provider.download(mode=request.mode, external_job_id=submission.external_job_id, destination=raw_output)
        _finalize_downloaded_output(
            raw_output,
            output,
            post_trim_duration_us=(int(segment["post_trim_duration_us"]) if segment.get("post_trim_duration_us") is not None else None),
        )
        if not output.is_file() or output.stat().st_size <= 0:
            raise H3RetryExecutionError("H3 重试最终输出为空")

        try:
            after = _current_segment(project_id, segment_id)
            still_current = str(after.get("input_fingerprint") or "") == str(segment["input_fingerprint"])
        except Exception:
            still_current = False
        completed = utcnow()
        with get_session() as session:
            row = session.get(GenerationAttempt, attempt_id)
            if row is None:
                raise H3RetryExecutionError("GenerationAttempt 下载后记录丢失")
            row.provider_status = final_provider_status
            row.output_path = str(output)
            row.status = "SUCCEEDED" if still_current else "STALE"
            row.error_message = None if still_current else "上游事实在 H3 重试期间变化，输出保留但不再作为当前结果"
            row.completed_at = completed
            row.updated_at = completed
            session.commit()
        result = get_generation_attempt_v1(attempt_id)
        if result is None:
            raise H3RetryExecutionError("GenerationAttempt 持久化后无法读取")
        return result
    except Exception as exc:
        completed = utcnow()
        with get_session() as session:
            row = session.get(GenerationAttempt, attempt_id)
            if row is not None:
                row.status = "FAILED"
                row.error_message = str(exc)[:4000]
                row.completed_at = completed
                row.updated_at = completed
                session.commit()
        if isinstance(exc, H3RetryExecutionError):
            raise
        if isinstance(exc, GenerationAttemptError):
            raise H3RetryExecutionError(str(exc)) from exc
        raise H3RetryExecutionError(str(exc)) from exc


__all__ = ["H3RetryExecutionError", "execute_generation_retry_v1"]
