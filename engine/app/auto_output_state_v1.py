"""Read-only product state for automatic downstream output.

The Output page must be able to ask "what is ready yet?" without probing every downstream
endpoint and turning a normal not-generated-yet lifecycle into HTTP 409 noise. This module is
deliberately side-effect free: it validates persisted dependency state and exposes only resources
that are safe for the UI to read. Actual generation remains owned by auto_output_v1.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select

from engine.app.episode_output_v1 import (
    EpisodeOutput,
    _digest as _episode_digest,
    _file_identity as _episode_file_identity,
    _subtitle_events as _episode_subtitle_events,
)
from engine.app.generation_attempt_v1 import GenerationAttempt
from engine.app.generation_segment_v1 import GenerationSegmentError, get_generation_segments_v1
from engine.app.generation_selection_v1 import GenerationSelection
from engine.app.postproduction_v1 import get_postproduction_plan_v1
from engine.app.review_issue_v1 import list_review_issues
from engine.app.studio_v2 import get_project, get_session, list_episode_records
from engine.app.target_dialogue_v1 import TargetDialogueError, get_target_dialogue_v1
from engine.app.target_localization_v1 import TargetLocalizationError, get_target_localization_v1


SCHEMA_VERSION = "auto-output-state-v1"


def _ready_audio_count(bundle: Mapping[str, Any]) -> tuple[int, int]:
    ready_rows = [
        row
        for row in bundle.get("dialogues") or []
        if isinstance(row, Mapping) and row.get("status") == "READY"
    ]
    return (
        sum(
            row.get("audio_status") == "READY" and bool(row.get("speech_duration_us"))
            for row in ready_rows
        ),
        len(ready_rows),
    )


def _payload(
    project_id: str,
    *,
    stage: str,
    message: str,
    episode_count: int,
    review_issue_count: int = 0,
    segment_count: int = 0,
    selected_segment_count: int = 0,
    postproduction_segment_count: int = 0,
    completed_episode_count: int = 0,
    can_read_generation_segments: bool = False,
    can_read_h3_quality: bool = False,
    can_read_postproduction: bool = False,
    can_read_outputs: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "stage": stage,
        "message": message,
        "review_issue_count": review_issue_count,
        "episode_count": episode_count,
        "segment_count": segment_count,
        "selected_segment_count": selected_segment_count,
        "postproduction_segment_count": postproduction_segment_count,
        "completed_episode_count": completed_episode_count,
        "can_read_generation_segments": can_read_generation_segments,
        "can_read_h3_quality": can_read_h3_quality,
        "can_read_postproduction": can_read_postproduction,
        "can_read_outputs": can_read_outputs,
        "active_task": None,
    }


def _selected_count(project_id: str, ready_segments: list[Mapping[str, Any]]) -> int:
    """Count only current, successful selected files without mutating stale selections."""

    if not ready_segments:
        return 0
    current = {
        str(segment.get("id") or ""): str(segment.get("input_fingerprint") or "")
        for segment in ready_segments
        if segment.get("id")
    }
    selected = 0
    with get_session() as session:
        rows = list(session.scalars(select(GenerationSelection).where(
            GenerationSelection.project_id == project_id,
        )).all())
        for row in rows:
            expected_fingerprint = current.get(row.generation_segment_id)
            if not expected_fingerprint or row.segment_input_fingerprint != expected_fingerprint:
                continue
            attempt = session.get(GenerationAttempt, row.selected_attempt_id)
            if (
                attempt is None
                or attempt.status != "SUCCEEDED"
                or attempt.segment_input_fingerprint != expected_fingerprint
                or not attempt.output_path
            ):
                continue
            path = Path(str(attempt.output_path))
            if path.is_file() and path.stat().st_size > 0:
                selected += 1
    return selected


def _episode_output_fingerprint(
    episode_id: str,
    generation_segments: list[Mapping[str, Any]],
    post_by_segment: Mapping[str, Mapping[str, Any]],
) -> str:
    """Rebuild the canonical EpisodeOutput fingerprint without materializing any row."""

    ordered = sorted(
        [dict(item) for item in generation_segments],
        key=lambda item: (
            int(item.get("target_start_us") or 0),
            int(item.get("target_end_us") or 0),
            str(item.get("id") or ""),
        ),
    )
    segments: list[dict[str, Any]] = []
    for segment in ordered:
        segment_id = str(segment.get("id") or "")
        post = post_by_segment.get(segment_id)
        post_status = str(post.get("status") or "MISSING") if post else "MISSING"
        raw_output = str(post.get("output_path") or "") if post else ""
        output = Path(raw_output) if raw_output else None
        output_ready = bool(
            post_status == "SUCCEEDED"
            and output is not None
            and output.is_file()
            and output.stat().st_size > 0
        )
        segments.append({
            "generation_segment_id": segment_id,
            "postproduction_fingerprint": str(
                post.get("postproduction_fingerprint") if post else segment.get("input_fingerprint") or ""
            ),
            "postproduction_status": post_status,
            "target_start_us": int(segment.get("target_start_us") or 0),
            "target_end_us": int(segment.get("target_end_us") or 0),
            "output_identity": _episode_file_identity(output) if output_ready else None,
        })

    return _episode_digest({
        "episode_id": episode_id,
        "segments": segments,
        "subtitles": _episode_subtitle_events(ordered),
    })


def _current_completed_episode_count(
    project_id: str,
    generation_plan: Mapping[str, Any],
    post_plan: Mapping[str, Any],
) -> int:
    generation_by_episode = {
        str(episode.get("episode_id") or ""): [
            dict(segment)
            for segment in episode.get("segments") or []
            if isinstance(segment, Mapping)
        ]
        for episode in generation_plan.get("episodes") or []
        if isinstance(episode, Mapping)
    }
    post_by_segment = {
        str(segment.get("generation_segment_id") or ""): dict(segment)
        for episode in post_plan.get("episodes") or []
        if isinstance(episode, Mapping)
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("generation_segment_id")
    }

    completed = 0
    with get_session() as session:
        rows = list(session.scalars(select(EpisodeOutput).where(
            EpisodeOutput.project_id == project_id,
        )).all())
        for row in rows:
            if row.status != "SUCCEEDED" or not row.output_path:
                continue
            output = Path(str(row.output_path))
            if not output.is_file() or output.stat().st_size <= 0:
                continue
            generation_segments = generation_by_episode.get(row.episode_id)
            if not generation_segments:
                continue
            expected = _episode_output_fingerprint(row.episode_id, generation_segments, post_by_segment)
            if row.input_fingerprint == expected:
                completed += 1
    return completed


def get_auto_output_state_v1(project_id: str) -> dict[str, Any]:
    """Return current downstream readiness without creating or regenerating any artifact."""

    if get_project(project_id) is None:
        raise LookupError("项目不存在")
    episode_count = len(list_episode_records(project_id))

    open_issues = list_review_issues(project_id, status="OPEN")
    if open_issues:
        return _payload(
            project_id,
            stage="review_gate",
            message=f"还有 {len(open_issues)} 项需要人工确认",
            episode_count=episode_count,
            review_issue_count=len(open_issues),
        )

    try:
        localization = get_target_localization_v1(project_id)
    except (TargetLocalizationError, LookupError):
        return _payload(
            project_id,
            stage="target_localization",
            message="目标人物 / 场景方案尚未生成，自动成片会从这里继续",
            episode_count=episode_count,
        )
    localization_review_count = int(localization.get("review_count") or 0)
    if localization_review_count:
        return _payload(
            project_id,
            stage="target_localization",
            message=f"目标人物 / 场景还有 {localization_review_count} 项需要确认",
            episode_count=episode_count,
            review_issue_count=localization_review_count,
        )

    try:
        dialogue = get_target_dialogue_v1(project_id)
    except (TargetDialogueError, LookupError):
        return _payload(
            project_id,
            stage="target_dialogue",
            message="目标对白尚未生成，自动成片会按项目语言和地区继续生成",
            episode_count=episode_count,
        )
    dialogue_review_count = int(dialogue.get("review_count") or 0)
    if dialogue_review_count:
        return _payload(
            project_id,
            stage="target_dialogue",
            message=f"目标对白有 {dialogue_review_count} 条旧的自动判断结果需要系统重新计算；不需要人工填写，自动成片会从这里继续",
            episode_count=episode_count,
        )

    audio_ready, audio_total = _ready_audio_count(dialogue)
    if audio_ready < audio_total:
        return _payload(
            project_id,
            stage="tts",
            message=f"正在等待目标语音完成（{audio_ready}/{audio_total}）",
            episode_count=episode_count,
        )

    try:
        generation_plan = get_generation_segments_v1(project_id)
    except (GenerationSegmentError, LookupError):
        return _payload(
            project_id,
            stage="generation_segments",
            message="目标对白已就绪，正在准备 Timing 与 MiniMax H3 镜头分段",
            episode_count=episode_count,
        )

    plan_segments = [
        segment
        for episode in generation_plan.get("episodes") or []
        if isinstance(episode, Mapping)
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping)
    ]
    segment_count = len(plan_segments)
    if int(generation_plan.get("review_count") or 0) > 0:
        return _payload(
            project_id,
            stage="generation_segments",
            message=f"有 {generation_plan.get('review_count')} 个生成分段需要确认",
            episode_count=episode_count,
            review_issue_count=int(generation_plan.get("review_count") or 0),
            segment_count=segment_count,
            can_read_generation_segments=True,
            can_read_h3_quality=True,
        )
    if int(generation_plan.get("waiting_audio_count") or 0) > 0:
        return _payload(
            project_id,
            stage="tts",
            message="生成分段仍在等待真实目标语音时长",
            episode_count=episode_count,
            segment_count=segment_count,
            can_read_generation_segments=True,
            can_read_h3_quality=True,
        )

    ready_segments = [segment for segment in plan_segments if segment.get("status") == "READY"]
    selected_segment_count = _selected_count(project_id, ready_segments)
    if selected_segment_count < len(ready_segments):
        return _payload(
            project_id,
            stage="h3_generation",
            message=f"MiniMax H3 镜头正在生成 / 质检（{selected_segment_count}/{len(ready_segments)}）",
            episode_count=episode_count,
            segment_count=segment_count,
            selected_segment_count=selected_segment_count,
            can_read_generation_segments=True,
            can_read_h3_quality=True,
        )

    post_plan = get_postproduction_plan_v1(project_id)
    post_segments = [
        segment
        for episode in post_plan.get("episodes") or []
        if isinstance(episode, Mapping)
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping)
    ]
    postproduction_segment_count = len(post_segments)
    can_read_postproduction = postproduction_segment_count > 0
    postproduction_complete = bool(post_segments) and (
        postproduction_segment_count == len(ready_segments)
        and all(segment.get("status") == "SUCCEEDED" for segment in post_segments)
    )
    if not postproduction_complete:
        return _payload(
            project_id,
            stage="postproduction",
            message="H3 可用镜头已就绪，正在执行口型、目标音轨和字幕后期",
            episode_count=episode_count,
            segment_count=segment_count,
            selected_segment_count=selected_segment_count,
            postproduction_segment_count=postproduction_segment_count,
            can_read_generation_segments=True,
            can_read_h3_quality=True,
            can_read_postproduction=can_read_postproduction,
        )

    completed_episode_count = _current_completed_episode_count(project_id, generation_plan, post_plan)
    can_read_outputs = completed_episode_count > 0
    if episode_count > 0 and completed_episode_count >= episode_count:
        return _payload(
            project_id,
            stage="complete",
            message="最终剧集已经全部完成",
            episode_count=episode_count,
            segment_count=segment_count,
            selected_segment_count=selected_segment_count,
            postproduction_segment_count=postproduction_segment_count,
            completed_episode_count=completed_episode_count,
            can_read_generation_segments=True,
            can_read_h3_quality=True,
            can_read_postproduction=True,
            can_read_outputs=True,
        )

    return _payload(
        project_id,
        stage="episode_output",
        message="后期分段已完成，正在拼接最终剧集并生成字幕",
        episode_count=episode_count,
        segment_count=segment_count,
        selected_segment_count=selected_segment_count,
        postproduction_segment_count=postproduction_segment_count,
        completed_episode_count=completed_episode_count,
        can_read_generation_segments=True,
        can_read_h3_quality=True,
        can_read_postproduction=True,
        can_read_outputs=can_read_outputs,
    )


__all__ = ["SCHEMA_VERSION", "get_auto_output_state_v1"]
