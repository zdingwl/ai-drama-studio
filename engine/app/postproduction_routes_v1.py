"""R10/R10.1 postproduction, subtitle and episode-output HTTP APIs."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from engine.app.audio_separator_provider_v1 import get_background_audio_provider_v1
from engine.app.episode_output_contract_v1 import EpisodeOutputPlanV1
from engine.app.episode_output_v1 import (
    assemble_ready_episodes_v1,
    compile_episode_outputs_v1,
    episode_output_subtitle_v1,
    episode_output_video_v1,
    get_episode_output_v1,
)
from engine.app.latentsync_provider_v1 import get_lip_sync_provider_v1
from engine.app.postproduction_audio_mix_v1 import run_ready_postproduction_with_audio_mix_v1
from engine.app.postproduction_contract_v1 import BackgroundAudioRuntimeStatusV1, LipSyncRuntimeStatusV1, PostProductionPlanV1
from engine.app.postproduction_review_v1 import retry_lip_sync_review_v1
from engine.app.postproduction_v1 import (
    compile_postproduction_plan_v1,
    get_postproduction_plan_v1,
)
from engine.app.studio_v2 import get_project
from engine.app.task_progress_v2 import (
    ACTIVE_TASK_STATUSES,
    create_task,
    fail_task,
    finish_task,
    list_project_tasks,
    start_task,
    update_task,
)


router = APIRouter(prefix="/api", tags=["postproduction"])
POSTPRODUCTION_TASK_TYPE = "POSTPRODUCTION_V1"
_HEAVY_TASK_TYPES = {
    POSTPRODUCTION_TASK_TYPE,
    "H3_GENERATE_READY_V1",
    "AUTO_REMAKE_PREP_V1",
    "EPISODE_SHOTS",
    "BATCH_SHOTS",
    "EPISODE_BREAKDOWN_P2",
    "BATCH_BREAKDOWN_P2",
    "ASSET_EXTRACTION_V3",
    "ASSET_EXTRACTION",
}


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


def _run_task(task_id: str, project_id: str) -> None:
    try:
        start_task(
            task_id,
            stage_key="postproduction",
            stage_label="口型、背景音、最终音轨与整集成片",
            message="正在处理 R10/R10.1 Selected Output 后期",
        )

        def post_progress(current: int, total: int, message: str) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=(current - 1) / max(1, total) * 68.0,
                stage_key="postproduction",
                stage_label="口型、目标对白与安全背景音",
                current_item=message,
                current_index=current,
                total_items=total,
                message=message,
            )

        post_result = run_ready_postproduction_with_audio_mix_v1(project_id, progress=post_progress)

        def assembly_progress(current: int, total: int, message: str) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=70.0 + (current - 1) / max(1, total) * 28.0,
                stage_key="episode_output",
                stage_label="字幕与整集成片",
                current_item=message,
                current_index=current,
                total_items=total,
                message=message,
            )

        assembly_result = assemble_ready_episodes_v1(project_id, progress=assembly_progress)
        post_plan = post_result.get("plan") or {}
        output_plan = assembly_result.get("plan") or {}
        post_failed = list(post_result.get("failed") or [])
        assembly_failed = list(assembly_result.get("failed") or [])
        review_count = int(post_plan.get("review_count") or 0)
        waiting_count = int(post_plan.get("waiting_count") or 0)
        output_waiting = int(output_plan.get("waiting_count") or 0)
        background_fallbacks = int((post_result.get("background_audio") or {}).get("fallback_count") or 0)
        warning_count = len(post_failed) + len(assembly_failed) + review_count + waiting_count + output_waiting
        result = {
            "project_id": project_id,
            "postproduction": post_result,
            "episode_outputs": assembly_result,
        }
        finish_task(
            task_id,
            result=result,
            status="READY_WITH_WARNINGS" if warning_count else "READY",
            message=(
                f"R10 完成：{post_result.get('succeeded_now', 0)} 段新后期，"
                f"{assembly_result.get('succeeded_now', 0)} 集新成片，"
                f"{review_count} 段需确认，{waiting_count + output_waiting} 项等待"
                if warning_count
                else (
                    f"R10 完成：{post_result.get('succeeded_now', 0)} 段新后期，"
                    f"{assembly_result.get('succeeded_now', 0)} 集新成片"
                    + (f"；{background_fallbacks} 段背景音安全降级" if background_fallbacks else "")
                )
            ),
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.get("/lip-sync/runtime", response_model=LipSyncRuntimeStatusV1)
def api_lip_sync_runtime():
    return get_lip_sync_provider_v1().status()


@router.get("/background-audio/runtime", response_model=BackgroundAudioRuntimeStatusV1)
def api_background_audio_runtime():
    return get_background_audio_provider_v1().status()


@router.post("/projects/{project_id}/postproduction/compile", response_model=PostProductionPlanV1)
def api_compile_postproduction(project_id: str):
    try:
        return compile_postproduction_plan_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/postproduction", response_model=PostProductionPlanV1)
def api_get_postproduction(project_id: str):
    try:
        return get_postproduction_plan_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/outputs", response_model=EpisodeOutputPlanV1)
def api_get_episode_outputs(project_id: str):
    try:
        return compile_episode_outputs_v1(project_id, persist=False)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/postproduction-segments/{segment_id}/retry-lip-sync")
def api_retry_lip_sync(project_id: str, segment_id: str):
    try:
        return retry_lip_sync_review_v1(project_id, segment_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/tasks/postproduction", status_code=202)
def api_start_postproduction(project_id: str, background: BackgroundTasks):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        post_plan = compile_postproduction_plan_v1(project_id)
        output_plan = compile_episode_outputs_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc

    ready_segments = [
        segment
        for episode in post_plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if segment.get("status") == "READY"
    ]
    ready_episodes = [episode for episode in output_plan.get("episodes") or [] if episode.get("status") == "READY"]
    if not ready_segments and not ready_episodes:
        raise HTTPException(status_code=409, detail="当前没有可执行的 R10 后期或整集拼接任务")

    needs_lip_sync = any(
        segment.get("lip_sync_mode") in {"LATENTSYNC_FULL_SEGMENT", "LATENTSYNC_TARGET_FACE_ROI"}
        for segment in ready_segments
    )
    if needs_lip_sync:
        runtime = get_lip_sync_provider_v1().status()
        if not runtime.get("ready"):
            raise HTTPException(
                status_code=409,
                detail="LatentSync 1.6 Runtime 尚未 READY；当前计划包含可见对白口型任务",
            )

    active = [
        task
        for task in list_project_tasks(project_id, limit=100)
        if task["status"] in ACTIVE_TASK_STATUSES and task["task_type"] in _HEAVY_TASK_TYPES
    ]
    existing = next((item for item in active if item["task_type"] == POSTPRODUCTION_TASK_TYPE), None)
    if existing is not None:
        return existing
    if active:
        raise HTTPException(status_code=409, detail="当前已有本地重任务正在执行，请先完成当前任务")

    task = create_task(
        project_id=project_id,
        task_type=POSTPRODUCTION_TASK_TYPE,
        title="口型、背景音、字幕与整集成片",
        progress_mode="indeterminate",
        total_items=len(ready_segments) + len(ready_episodes),
        deduplicate_active=False,
    )
    background.add_task(_run_task, task["id"], project_id)
    return task


@router.get("/postproduction-segments/{segment_id}/video")
def api_postproduction_video(segment_id: str, project_id: str):
    try:
        plan = get_postproduction_plan_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc
    row = next(
        (
            segment
            for episode in plan.get("episodes") or []
            for segment in episode.get("segments") or []
            if segment.get("generation_segment_id") == segment_id
        ),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="PostProductionSegment 不存在")
    path = (
        Path(str(row.get("output_path")))
        if row.get("status") == "SUCCEEDED" and row.get("output_path")
        else None
    )
    if path is None or not path.is_file() or path.stat().st_size <= 0:
        raise HTTPException(status_code=409, detail="当前 PostProductionSegment 尚无成功输出")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/episodes/{episode_id}/final-video")
def api_episode_final_video(episode_id: str, project_id: str):
    row = get_episode_output_v1(project_id, episode_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EpisodeOutput 不存在")
    path = episode_output_video_v1(project_id, episode_id)
    if path is None:
        raise HTTPException(status_code=409, detail="当前剧集尚无成功成片")
    safe_name = f"{row['episode_title']}.mp4".replace("/", "_").replace("\\", "_")
    return FileResponse(path, media_type="video/mp4", filename=safe_name)


@router.get("/episodes/{episode_id}/subtitles")
def api_episode_subtitles(episode_id: str, project_id: str):
    row = get_episode_output_v1(project_id, episode_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EpisodeOutput 不存在")
    path = episode_output_subtitle_v1(project_id, episode_id)
    if path is None:
        raise HTTPException(status_code=409, detail="当前剧集尚无字幕文件")
    safe_name = f"{row['episode_title']}.srt".replace("/", "_").replace("\\", "_")
    return FileResponse(path, media_type="application/x-subrip; charset=utf-8", filename=safe_name)


__all__ = ["POSTPRODUCTION_TASK_TYPE", "router"]
