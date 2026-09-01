"""R9 sequential H3 generation -> QC -> retry -> selected-output orchestration."""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping

from engine.app.generation_segment_v1 import compile_generation_segments_v1
from engine.app.generation_selection_v1 import selected_generation_output_v1
from engine.app.h3_qc_core_v1 import (
    current_attempts_for_segment_v1,
    current_generation_segment_v1,
    get_generation_quality_check_v1,
    get_generation_quality_summary_v1,
    publish_h3_qc_review_issue_v1,
    run_generation_attempt_qc_v1,
)
from engine.app.h3_reference_assets_v1 import ensure_target_character_references_v1, ensure_target_scene_references_v1
from engine.app.h3_retry_execution_v1 import H3RetryExecutionError, execute_generation_retry_v1


ProgressCallback = Callable[[int, int, str], None]


def _max_auto_attempts() -> int:
    try:
        value = int(os.getenv("AI_DRAMA_H3_QC_MAX_ATTEMPTS", "3"))
    except ValueError:
        value = 3
    return max(1, min(5, value))


def _latest_retry_feedback(attempts: list[dict[str, Any]]) -> str | None:
    for attempt in reversed(attempts):
        qc = get_generation_quality_check_v1(str(attempt["id"]))
        if qc and qc.get("retry_instruction"):
            return str(qc["retry_instruction"])
    return None


def _qc_existing_successes(project_id: str, segment: Mapping[str, Any], attempts: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Return (stop_reason, retry_feedback). PASS auto-selects and returns no stop reason."""

    retry_feedback: str | None = None
    for attempt in attempts:
        if attempt.get("status") != "SUCCEEDED":
            continue
        qc = get_generation_quality_check_v1(str(attempt["id"]))
        if qc is None or qc.get("status") == "WAITING_MODEL":
            qc = run_generation_attempt_qc_v1(str(attempt["id"]))
        if qc["status"] == "PASS":
            return None, None
        if qc["status"] == "WAITING_MODEL":
            return str(qc["reason"]), retry_feedback
        if qc["status"] == "REVIEW":
            return str(qc["reason"]), retry_feedback
        if qc["status"] == "RETRY" and qc.get("retry_instruction"):
            retry_feedback = str(qc["retry_instruction"])
    return None, retry_feedback


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
            progress(index, len(segments), f"生成 + QC {index}/{len(segments)} · Shot {segment.get('shot_ordinal')} · Segment {segment.get('shot_segment_index')}")

        if selected_generation_output_v1(project_id, segment_id) is not None:
            reused_selected += 1
            continue

        attempts = current_attempts_for_segment_v1(project_id, segment_id, fingerprint)
        stop_reason, retry_feedback = _qc_existing_successes(project_id, segment, attempts)
        if selected_generation_output_v1(project_id, segment_id) is not None:
            selected_now += 1
            continue
        if stop_reason:
            latest_qc = next((get_generation_quality_check_v1(str(item["id"])) for item in reversed(attempts) if item.get("status") == "SUCCEEDED"), None)
            if latest_qc and latest_qc.get("status") == "WAITING_MODEL":
                waiting.append({"segment_id": segment_id, "reason": stop_reason})
            else:
                publish_h3_qc_review_issue_v1(project_id, segment, stop_reason)
                review.append({"segment_id": segment_id, "reason": stop_reason})
            continue

        attempts_used = len(attempts)
        while attempts_used < max_attempts:
            try:
                attempt = execute_generation_retry_v1(
                    project_id,
                    segment_id,
                    retry_index=attempts_used + 1,
                    retry_feedback=retry_feedback,
                )
                generated_attempts += 1
            except H3RetryExecutionError as exc:
                attempts_used += 1
                message = str(exc)
                target = {"segment_id": segment_id, "error": message}
                if "参考资产" in message or "连续段" in message or "Selected Output" in message:
                    waiting.append({"segment_id": segment_id, "reason": message})
                    break
                generation_failures.append(target)
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
                reason = str(qc["reason"])
                publish_h3_qc_review_issue_v1(project_id, segment, reason)
                review.append({"segment_id": segment_id, "reason": reason})
                break
            retry_feedback = str(qc.get("retry_instruction") or "").strip() or retry_feedback

        if selected_generation_output_v1(project_id, segment_id) is not None:
            continue
        current_attempts = current_attempts_for_segment_v1(project_id, segment_id, fingerprint)
        latest_qc = next(
            (
                get_generation_quality_check_v1(str(item["id"]))
                for item in reversed(current_attempts)
                if item.get("status") == "SUCCEEDED"
            ),
            None,
        )
        if latest_qc and latest_qc.get("status") == "RETRY" and len(current_attempts) >= max_attempts:
            reason = f"H3 已自动尝试 {len(current_attempts)} 次仍未通过 QC：{latest_qc.get('reason')}"
            publish_h3_qc_review_issue_v1(project_id, segment, reason)
            review.append({"segment_id": segment_id, "reason": reason})

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
        "quality_summary": get_generation_quality_summary_v1(project_id),
    }


def run_manual_qc_retry_v1(project_id: str, segment_id: str) -> dict[str, Any]:
    segment = current_generation_segment_v1(project_id, segment_id)
    if segment.get("status") != "READY":
        raise ValueError("当前 GenerationSegment 尚不可重新生成")
    attempts = current_attempts_for_segment_v1(project_id, segment_id, str(segment["input_fingerprint"]))
    attempt = execute_generation_retry_v1(
        project_id,
        segment_id,
        retry_index=len(attempts) + 1,
        retry_feedback=_latest_retry_feedback(attempts),
    )
    qc = run_generation_attempt_qc_v1(str(attempt["id"])) if attempt.get("status") == "SUCCEEDED" else None
    if qc and qc.get("status") in {"RETRY", "REVIEW"}:
        publish_h3_qc_review_issue_v1(project_id, segment, str(qc.get("reason") or "手动重试后仍未通过 H3 QC"))
    return {"attempt": attempt, "quality_check": qc, "quality_summary": get_generation_quality_summary_v1(project_id)}


__all__ = ["run_generation_with_qc_v1", "run_manual_qc_retry_v1"]
