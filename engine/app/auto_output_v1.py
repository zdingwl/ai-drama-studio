"""Automatic downstream continuation from current SourceDramaSnapshot to final episode output.

This coordinator deliberately does not rerun media ingest, shot detection, breakdown or asset
extraction.  It is used by the product-facing Output page when upstream source truth is already
available and there are no human ReviewIssues.  Every step is idempotent and reuses persisted
results where their dependency anchors are still current.

Human ambiguity and infrastructure failures are separate states:
- real ReviewIssue -> READY_WITH_WARNINGS and wait for the user;
- local model/runtime unavailable -> READY_WITH_WARNINGS and tell the user what runtime to restore;
- unexpected exception -> FAILED task via run_auto_output_task().
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from engine.app.episode_output_v1 import assemble_ready_episodes_v1, compile_episode_outputs_v1
from engine.app.generation_segment_v1 import compile_generation_segments_v1
from engine.app.generation_selection_v1 import selected_generation_output_v1
from engine.app.h3_qc_v1 import run_generation_with_qc_v1
from engine.app.latentsync_provider_v1 import get_lip_sync_provider_v1
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.postproduction_audio_mix_v1 import run_ready_postproduction_with_audio_mix_v1
from engine.app.postproduction_v1 import compile_postproduction_plan_v1
from engine.app.remake_timeline_v1 import generate_remake_timeline_v1
from engine.app.review_issue_v1 import list_review_issues
from engine.app.target_dialogue_pipeline_v1 import (
    run_target_dialogue_pipeline_v1,
    validate_target_dialogue_dependencies_v1,
)
from engine.app.target_dialogue_v1 import (
    TargetDialogueError,
    get_target_dialogue_v1,
    materialize_target_dialogue_audio_v1,
)
from engine.app.target_localization_runtime_guard_v1 import (
    require_target_localization_runtime_v1,
    validate_target_localization_generation_v1,
)
from engine.app.target_localization_v1 import (
    TargetLocalizationError,
    generate_target_localization_v1,
    get_target_localization_v1,
)
from engine.app.task_progress_v2 import fail_task, finish_task, start_task, update_task


AUTO_OUTPUT_TASK_TYPE = "AUTO_OUTPUT_V1"
ProgressCallback = Callable[[float, str, str, str], None]


def _blocked(stage: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "task_status": "READY_WITH_WARNINGS",
        "stage": stage,
        "message": message,
        **details,
    }


def _ready(message: str, **details: Any) -> dict[str, Any]:
    return {
        "task_status": "READY",
        "stage": "episode_output",
        "message": message,
        **details,
    }


def _emit(progress: ProgressCallback | None, percent: float, stage: str, label: str, message: str) -> None:
    if progress is not None:
        progress(percent, stage, label, message)


def _pending_h3_segments(project_id: str, plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for episode in plan.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        for segment in episode.get("segments") or []:
            if not isinstance(segment, Mapping) or segment.get("status") != "READY" or not segment.get("id"):
                continue
            segment_id = str(segment["id"])
            if selected_generation_output_v1(project_id, segment_id) is None:
                pending.append(dict(segment))
    return pending


def _missing_h3_modes(pending: list[Mapping[str, Any]]) -> list[str]:
    if not pending:
        return []
    runtime = get_video_generation_provider_v1("MINIMAX_H3_LOCAL").status()
    required = {"FL2VA"}
    if any(item.get("generation_mode") == "REF2VA" for item in pending):
        required.add("REF2VA")
    missing: list[str] = []
    if "FL2VA" in required and not bool((runtime.get("fl2va") or {}).get("ready")):
        missing.append("FL2VA")
    if "REF2VA" in required and not bool((runtime.get("ref2va") or {}).get("ready")):
        missing.append("Ref2VA")
    return missing


def _ready_audio_count(bundle: Mapping[str, Any]) -> tuple[int, int]:
    ready_rows = [
        row for row in bundle.get("dialogues") or []
        if isinstance(row, Mapping) and row.get("status") == "READY"
    ]
    return (
        sum(row.get("audio_status") == "READY" and bool(row.get("speech_duration_us")) for row in ready_rows),
        len(ready_rows),
    )


def _post_ready_segments(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(segment)
        for episode in plan.get("episodes") or []
        if isinstance(episode, Mapping)
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("status") == "READY"
    ]


def run_auto_output_pipeline_v1(project_id: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
    """Continue only the missing downstream work for one project."""

    _emit(progress, 3.0, "review_gate", "检查人工确认", "正在确认当前项目没有尚未处理的人工决策")
    open_issues = list_review_issues(project_id, status="OPEN")
    if open_issues:
        return _blocked(
            "review_gate",
            f"还有 {len(open_issues)} 项需要人工确认；处理完成后系统会继续生成成片",
            review_issue_count=len(open_issues),
        )

    _emit(progress, 8.0, "target_localization", "目标人物 / 场景", "正在检查目标人物与场景方案")
    try:
        localization = get_target_localization_v1(project_id)
    except TargetLocalizationError:
        require_target_localization_runtime_v1(project_id)
        localization = validate_target_localization_generation_v1(
            project_id,
            generate_target_localization_v1(project_id),
        )
    if int(localization.get("review_count") or 0) > 0:
        return _blocked(
            "target_localization",
            f"目标人物/场景还有 {localization.get('review_count')} 项真正需要确认；确认后系统会继续",
            target_localization=localization,
        )

    _emit(progress, 18.0, "target_dialogue", "目标对白", "正在按项目语言和地区自动生成目标对白")
    try:
        dialogue = get_target_dialogue_v1(project_id)
        validate_target_dialogue_dependencies_v1(project_id)
    except TargetDialogueError:
        dialogue = run_target_dialogue_pipeline_v1(project_id, synthesize_audio=True)

    if int(dialogue.get("review_count") or 0) > 0:
        return _blocked(
            "target_dialogue",
            f"目标对白还有 {dialogue.get('review_count')} 条真实语义问题需要确认；确认后系统会继续",
            target_dialogue=dialogue,
        )

    audio_ready, audio_total = _ready_audio_count(dialogue)
    if audio_ready < audio_total:
        _emit(progress, 27.0, "tts", "目标语音 TTS", f"正在生成目标语音 {audio_ready}/{audio_total}")
        dialogue = materialize_target_dialogue_audio_v1(project_id)
        audio_ready, audio_total = _ready_audio_count(dialogue)
    if audio_ready < audio_total:
        failed_audio = [
            {
                "dialogue_id": row.get("id"),
                "audio_status": row.get("audio_status"),
                "error_message": row.get("error_message"),
            }
            for row in dialogue.get("dialogues") or []
            if isinstance(row, Mapping)
            and row.get("status") == "READY"
            and row.get("audio_status") != "READY"
        ]
        return _blocked(
            "tts",
            f"目标对白已经自动生成，但目标语音尚未完成（{audio_ready}/{audio_total}）；恢复本地 Qwen3-TTS 后可直接继续",
            blocked_by="TTS_RUNTIME",
            target_dialogue=dialogue,
            failed_audio=failed_audio[:20],
        )

    _emit(progress, 35.0, "timing", "对白时长 / Timing", "正在根据真实目标语音时长自动调整镜头时间轴")
    timeline = generate_remake_timeline_v1(project_id)
    if int(timeline.get("review_count") or 0) > 0:
        return _blocked(
            "timing",
            f"有 {timeline.get('review_count')} 个极端时长镜头需要人工决定；其余镜头已经自动规划",
            remake_timeline=timeline,
        )
    if int(timeline.get("waiting_audio_count") or 0) > 0:
        return _blocked(
            "timing",
            "目标时间轴仍在等待真实 TTS 时长；恢复目标语音生成后可继续",
            blocked_by="TTS_RUNTIME",
            remake_timeline=timeline,
        )

    _emit(progress, 42.0, "generation_segments", "生成镜头计划", "正在编译 MiniMax H3 可执行镜头分段")
    generation_plan = compile_generation_segments_v1(project_id)
    if int(generation_plan.get("review_count") or 0) > 0:
        return _blocked(
            "generation_segments",
            f"有 {generation_plan.get('review_count')} 个生成分段需要人工确认",
            generation_segments=generation_plan,
        )
    if int(generation_plan.get("waiting_audio_count") or 0) > 0:
        return _blocked(
            "generation_segments",
            "生成镜头计划仍在等待真实目标语音",
            blocked_by="TTS_RUNTIME",
            generation_segments=generation_plan,
        )

    pending_h3 = _pending_h3_segments(project_id, generation_plan)
    if pending_h3:
        missing_modes = _missing_h3_modes(pending_h3)
        if missing_modes:
            return _blocked(
                "h3_runtime",
                "本地 MiniMax H3 尚未就绪；恢复 " + " / ".join(missing_modes) + " 后可直接继续生成",
                blocked_by="H3_RUNTIME",
                missing_modes=missing_modes,
                pending_h3_count=len(pending_h3),
            )

        _emit(progress, 50.0, "h3_generation", "MiniMax H3 生成 + 自动质检", f"正在生成并自动质检 {len(pending_h3)} 个目标镜头")

        def h3_progress(current: int, total: int, message: str) -> None:
            percent = 50.0 + (max(1, current) - 1) / max(1, total) * 25.0
            _emit(progress, percent, "h3_generation", "MiniMax H3 生成 + 自动质检", message)

        h3_result = run_generation_with_qc_v1(project_id, progress=h3_progress)
        h3_failures = list(h3_result.get("generation_failures") or [])
        h3_waiting = list(h3_result.get("waiting") or [])
        h3_review = list(h3_result.get("review") or [])
        reference_failures = list((h3_result.get("character_references") or {}).get("failed") or []) + list(
            (h3_result.get("scene_references") or {}).get("failed") or []
        )
        if h3_review:
            return _blocked(
                "h3_qc",
                f"H3 已自动重试和质检，仍有 {len(h3_review)} 个镜头需要人工判断",
                h3=h3_result,
            )
        if h3_failures or h3_waiting or reference_failures:
            return _blocked(
                "h3_generation",
                f"H3 自动生成尚有 {len(h3_failures) + len(h3_waiting) + len(reference_failures)} 项未完成；恢复本地生成环境后可继续",
                blocked_by="H3_RUNTIME",
                h3=h3_result,
            )
    else:
        h3_result = {"reused_selected": int(generation_plan.get("segment_count") or 0), "selected_now": 0}

    # H3 QC may have published a real ReviewIssue. Never continue to postproduction past it.
    open_issues = list_review_issues(project_id, status="OPEN")
    if open_issues:
        return _blocked(
            "h3_qc",
            f"生成质检后还有 {len(open_issues)} 项需要人工确认；处理后系统会从这里继续",
            review_issue_count=len(open_issues),
            h3=h3_result,
        )

    _emit(progress, 80.0, "postproduction", "口型 / 目标音轨 / 字幕", "正在准备自动口型与最终音轨")
    post_plan = compile_postproduction_plan_v1(project_id)
    if int(post_plan.get("review_count") or 0) > 0:
        return _blocked(
            "postproduction",
            f"口型定位有 {post_plan.get('review_count')} 项需要人工确认",
            postproduction=post_plan,
        )

    ready_post = _post_ready_segments(post_plan)
    needs_lip_sync = any(
        row.get("lip_sync_mode") in {"LATENTSYNC_FULL_SEGMENT", "LATENTSYNC_TARGET_FACE_ROI"}
        for row in ready_post
    )
    if needs_lip_sync and not bool(get_lip_sync_provider_v1().status().get("ready")):
        return _blocked(
            "lip_sync_runtime",
            "本地 LatentSync 口型模型尚未就绪；恢复模型后可直接继续，不需要重新生成 H3",
            blocked_by="LIPSYNC_RUNTIME",
            postproduction=post_plan,
        )

    post_result: dict[str, Any] = {"plan": post_plan, "succeeded_now": 0, "failed": []}
    if ready_post:
        def post_progress(current: int, total: int, message: str) -> None:
            percent = 82.0 + (max(1, current) - 1) / max(1, total) * 10.0
            _emit(progress, percent, "postproduction", "口型 / 目标音轨 / 字幕", message)

        post_result = run_ready_postproduction_with_audio_mix_v1(project_id, progress=post_progress)
        post_plan = post_result.get("plan") or post_plan
        post_failed = list(post_result.get("failed") or [])
        if int(post_plan.get("review_count") or 0) > 0:
            return _blocked(
                "postproduction",
                f"自动口型处理后还有 {post_plan.get('review_count')} 项需要人工确认",
                postproduction=post_result,
            )
        if post_failed:
            return _blocked(
                "postproduction",
                f"自动后期有 {len(post_failed)} 个分段执行失败；可直接重试，不需要重新生成上游内容",
                blocked_by="POSTPRODUCTION_RUNTIME",
                postproduction=post_result,
            )

    _emit(progress, 95.0, "episode_output", "字幕与整集成片", "正在拼接最终剧集并生成字幕")
    assembly = assemble_ready_episodes_v1(project_id)
    output_plan = assembly.get("plan") or compile_episode_outputs_v1(project_id)
    assembly_failed = list(assembly.get("failed") or [])
    waiting_count = int(output_plan.get("waiting_count") or 0)
    succeeded_count = int(output_plan.get("succeeded_count") or 0)
    episode_count = int(output_plan.get("episode_count") or len(output_plan.get("episodes") or []))

    if assembly_failed or waiting_count:
        return _blocked(
            "episode_output",
            f"最终成片已完成 {succeeded_count}/{episode_count} 集，仍有 {len(assembly_failed) + waiting_count} 项等待自动处理",
            blocked_by="EPISODE_OUTPUT",
            postproduction=post_result,
            episode_outputs=assembly,
        )

    return _ready(
        f"自动成片完成：{succeeded_count}/{episode_count} 集可播放和下载",
        target_dialogue=dialogue,
        remake_timeline=timeline,
        generation_segments=generation_plan,
        h3=h3_result,
        postproduction=post_result,
        episode_outputs=assembly,
    )


def run_auto_output_task(task_id: str, project_id: str) -> None:
    """BackgroundTask wrapper with persisted progress and failure recovery semantics."""

    try:
        start_task(
            task_id,
            stage_key="review_gate",
            stage_label="继续自动生成成片",
            message="正在从当前项目进度继续目标对白、H3、口型和整集成片",
        )

        def progress(percent: float, stage: str, label: str, message: str) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=max(0.0, min(99.0, percent)),
                stage_key=stage,
                stage_label=label,
                message=message,
            )

        result = run_auto_output_pipeline_v1(project_id, progress=progress)
        finish_task(
            task_id,
            result=result,
            status=str(result.get("task_status") or "READY_WITH_WARNINGS"),
            message=str(result.get("message") or "自动成片流程已结束"),
        )
    except Exception as exc:
        fail_task(task_id, exc)


__all__ = [
    "AUTO_OUTPUT_TASK_TYPE",
    "run_auto_output_pipeline_v1",
    "run_auto_output_task",
]
