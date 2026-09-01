"""R8 H3 Context / GenerationAttempt / background generation APIs."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from engine.app.generation_attempt_v1 import (
    GenerationAttemptError,
    get_generation_attempt_v1,
    list_generation_attempts_v1,
    run_ready_generation_segments_v1,
)
from engine.app.generation_segment_v1 import GenerationSegmentError, get_generation_segments_v1
from engine.app.h3_context_compiler_v1 import H3ContextCompilerError, compile_h3_context_v1
from engine.app.h3_context_contract_v1 import (
    GenerationAttemptProjectSummaryV1,
    H3CompiledContextV1,
)
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
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


router = APIRouter(tags=["h3-generation"])
H3_BATCH_TASK_TYPE = "H3_GENERATE_READY_V1"
_HEAVY_TASK_TYPES = {
    H3_BATCH_TASK_TYPE,
    "AUTO_REMAKE_PREP_V1",
    "EPISODE_SHOTS",
    "BATCH_SHOTS",
    "EPISODE_BREAKDOWN_P2",
    "BATCH_BREAKDOWN_P2",
    "ASSET_EXTRACTION_V3",
    "ASSET_EXTRACTION",
}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (GenerationAttemptError, GenerationSegmentError, H3ContextCompilerError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=409, detail=f"H3 生成当前不可用：{exc}")


def _run_h3_batch_task(task_id: str, project_id: str) -> None:
    try:
        start_task(
            task_id,
            stage_key="h3_references",
            stage_label="准备 H3 目标参考",
            message="正在自动补齐目标人物 / 本土化场景参考资产",
        )

        def progress(current: int, total: int, message: str) -> None:
            percent = 5.0 + (current - 1) / max(1, total) * 92.0
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=percent,
                stage_key="h3_generation",
                stage_label="本地 MiniMax H3 生成",
                current_item=message,
                current_index=current,
                total_items=total,
                message=message,
            )

        result = run_ready_generation_segments_v1(project_id, progress=progress)
        failed = list(result.get("failed") or [])
        waiting = list(result.get("waiting") or [])
        reference_failures = list((result.get("character_references") or {}).get("failed") or []) + list(
            (result.get("scene_references") or {}).get("failed") or []
        )
        warning_count = len(failed) + len(waiting) + len(reference_failures)
        finish_task(
            task_id,
            result=result,
            status="READY_WITH_WARNINGS" if warning_count else "READY",
            message=(
                f"H3 本地生成完成：{result.get('succeeded_now', 0)} 段新生成，"
                f"{result.get('reused_success', 0)} 段复用，{warning_count} 项尚待自动重试/处理"
                if warning_count
                else f"H3 本地生成完成：{result.get('succeeded_now', 0)} 段新生成，{result.get('reused_success', 0)} 段复用"
            ),
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.get("/projects/{project_id}/generation-attempts", response_model=GenerationAttemptProjectSummaryV1)
def api_list_generation_attempts(project_id: str):
    try:
        return list_generation_attempts_v1(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/generation-segments/{segment_id}/h3-context", response_model=H3CompiledContextV1)
def api_compile_h3_context(segment_id: str, project_id: str):
    try:
        return compile_h3_context_v1(project_id, segment_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/projects/{project_id}/tasks/h3-generate-ready", status_code=202)
def api_start_h3_generate_ready(project_id: str, background: BackgroundTasks):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    runtime = get_video_generation_provider_v1("MINIMAX_H3_LOCAL").status()
    if not runtime.get("ready"):
        raise HTTPException(status_code=409, detail="本地 MiniMax H3 Runtime 尚未 READY，请先启动 FL2VA / Ref2VA 服务")
    try:
        plan = get_generation_segments_v1(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    ready_count = sum(
        segment.get("status") == "READY"
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
    )
    if ready_count <= 0:
        raise HTTPException(status_code=409, detail="当前没有可提交 H3 的 GenerationSegment；请先完成自动处理或待确认项")

    active = [
        task for task in list_project_tasks(project_id, limit=100)
        if task["status"] in ACTIVE_TASK_STATUSES and task["task_type"] in _HEAVY_TASK_TYPES
    ]
    existing = next((item for item in active if item["task_type"] == H3_BATCH_TASK_TYPE), None)
    if existing is not None:
        return existing
    if active:
        raise HTTPException(status_code=409, detail="当前已有本地重任务正在执行，请先让当前任务完成")

    task = create_task(
        project_id=project_id,
        task_type=H3_BATCH_TASK_TYPE,
        title="MiniMax H3 生成可用镜头",
        progress_mode="indeterminate",
        total_items=ready_count,
        deduplicate_active=False,
    )
    background.add_task(_run_h3_batch_task, task["id"], project_id)
    return task


@router.get("/generation-attempts/{attempt_id}/video")
def api_generation_attempt_video(attempt_id: str):
    attempt = get_generation_attempt_v1(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="GenerationAttempt 不存在")
    if attempt.get("status") != "SUCCEEDED" or not attempt.get("output_path"):
        raise HTTPException(status_code=409, detail="当前 GenerationAttempt 没有可播放成功输出")
    path = Path(str(attempt["output_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="GenerationAttempt 输出文件不存在")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


__all__ = ["H3_BATCH_TASK_TYPE", "router"]
