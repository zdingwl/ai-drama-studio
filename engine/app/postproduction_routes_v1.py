"""R10 postproduction HTTP APIs and background execution."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from engine.app.latentsync_provider_v1 import get_lip_sync_provider_v1
from engine.app.postproduction_contract_v1 import LipSyncRuntimeStatusV1, PostProductionPlanV1
from engine.app.postproduction_v1 import (
    PostProductionError,
    compile_postproduction_plan_v1,
    get_postproduction_segment_v1,
    postproduction_output_v1,
    run_ready_postproduction_v1,
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
            stage_label="口型与最终目标音轨",
            message="正在处理 R10 Selected Output 后期",
        )

        def progress(current: int, total: int, message: str) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=(current - 1) / max(1, total) * 96.0,
                stage_key="postproduction",
                stage_label="口型与最终目标音轨",
                current_item=message,
                current_index=current,
                total_items=total,
                message=message,
            )

        result = run_ready_postproduction_v1(project_id, progress=progress)
        plan = result.get("plan") or {}
        failed = list(result.get("failed") or [])
        review_count = int(plan.get("review_count") or 0)
        waiting_count = int(plan.get("waiting_count") or 0)
        warning_count = len(failed) + review_count + waiting_count
        finish_task(
            task_id,
            result=result,
            status="READY_WITH_WARNINGS" if warning_count else "READY",
            message=(
                f"R10 后期完成：{result.get('succeeded_now', 0)} 段新完成，"
                f"{review_count} 段需确认，{waiting_count} 段等待上游/本地模型"
                if warning_count
                else f"R10 后期完成：{result.get('succeeded_now', 0)} 段新完成"
            ),
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.get("/lip-sync/runtime", response_model=LipSyncRuntimeStatusV1)
def api_lip_sync_runtime():
    return get_lip_sync_provider_v1().status()


@router.post("/projects/{project_id}/postproduction/compile", response_model=PostProductionPlanV1)
def api_compile_postproduction(project_id: str):
    try:
        return compile_postproduction_plan_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/postproduction", response_model=PostProductionPlanV1)
def api_get_postproduction(project_id: str):
    try:
        return compile_postproduction_plan_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/tasks/postproduction", status_code=202)
def api_start_postproduction(project_id: str, background: BackgroundTasks):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        plan = compile_postproduction_plan_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc

    ready = [
        segment
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if segment.get("status") == "READY"
    ]
    if not ready:
        raise HTTPException(status_code=409, detail="当前没有可执行的 R10 PostProductionSegment")
    needs_lip_sync = any(
        segment.get("lip_sync_mode") in {"LATENTSYNC_FULL_SEGMENT", "LATENTSYNC_TARGET_FACE_ROI"}
        for segment in ready
    )
    if needs_lip_sync:
        runtime = get_lip_sync_provider_v1().status()
        if not runtime.get("ready"):
            raise HTTPException(
                status_code=409,
                detail="LatentSync 1.6 Runtime 尚未 READY；无可见对白的分段不需要它，但当前计划包含可见对白口型任务",
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
        title="口型与最终音轨后期",
        progress_mode="indeterminate",
        total_items=len(ready),
        deduplicate_active=False,
    )
    background.add_task(_run_task, task["id"], project_id)
    return task


@router.get("/postproduction-segments/{segment_id}/video")
def api_postproduction_video(segment_id: str, project_id: str):
    row = get_postproduction_segment_v1(segment_id)
    if row is None or row.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="PostProductionSegment 不存在")
    path = postproduction_output_v1(project_id, segment_id)
    if path is None:
        raise HTTPException(status_code=409, detail="当前 PostProductionSegment 尚无成功输出")
    return FileResponse(path, media_type="video/mp4", filename=Path(path).name)


__all__ = ["POSTPRODUCTION_TASK_TYPE", "router"]
