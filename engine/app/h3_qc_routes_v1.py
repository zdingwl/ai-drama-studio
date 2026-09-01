"""R9 H3 QC, selected-output and manual retry APIs."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from engine.app.generation_attempt_v1 import get_generation_attempt_v1
from engine.app.generation_selection_v1 import GenerationSelectionError, get_generation_selection_v1
from engine.app.h3_qc_contract_v1 import GenerationQualityCheckV1, GenerationQualityProjectSummaryV1, GenerationSelectionV1
from engine.app.h3_qc_v1 import (
    H3QualityError,
    get_generation_quality_summary_v1,
    manual_select_generation_attempt_v1,
    run_generation_attempt_qc_v1,
    run_manual_qc_retry_v1,
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
)


# Mounted by h3_generation_routes_v1 under its /api prefix so H3 generation/QC stays one
# product API surface and all R9 ORM tables are imported before init_database().
router = APIRouter(tags=["h3-quality"])
H3_QC_RETRY_TASK_TYPE = "H3_QC_RETRY_V1"


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (H3QualityError, GenerationSelectionError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=409, detail=f"H3 QC 当前不可用：{exc}")


@router.get("/projects/{project_id}/h3-quality", response_model=GenerationQualityProjectSummaryV1)
def api_h3_quality(project_id: str):
    try:
        return get_generation_quality_summary_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/generation-attempts/{attempt_id}/quality-check", response_model=GenerationQualityCheckV1)
def api_check_generation_attempt(attempt_id: str):
    try:
        return run_generation_attempt_qc_v1(attempt_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/generation-attempts/{attempt_id}/select", response_model=GenerationSelectionV1)
def api_select_generation_attempt(attempt_id: str):
    try:
        return manual_select_generation_attempt_v1(attempt_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/generation-segments/{segment_id}/selected-video")
def api_selected_generation_video(segment_id: str, project_id: str):
    selection = get_generation_selection_v1(project_id, segment_id)
    if selection is None:
        raise HTTPException(status_code=404, detail="当前 GenerationSegment 还没有 Selected Output")
    attempt = get_generation_attempt_v1(str(selection["selected_attempt_id"]))
    path = Path(str(attempt.get("output_path") or "")) if attempt else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Selected Output 文件不存在")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


def _run_manual_retry_task(task_id: str, project_id: str, segment_id: str) -> None:
    try:
        start_task(
            task_id,
            stage_key="h3_qc_retry",
            stage_label="重新生成未通过镜头",
            message="正在根据上一版 QC 反馈重新生成并再次质检",
        )
        result = run_manual_qc_retry_v1(project_id, segment_id)
        qc = result.get("quality_check") or {}
        passed = qc.get("status") == "PASS"
        finish_task(
            task_id,
            result=result,
            status="READY" if passed else "READY_WITH_WARNINGS",
            message="重新生成并通过 H3 QC" if passed else f"重新生成完成，但 QC 状态为 {qc.get('status') or 'UNKNOWN'}",
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.post("/projects/{project_id}/generation-segments/{segment_id}/tasks/h3-qc-retry", status_code=202)
def api_start_manual_qc_retry(project_id: str, segment_id: str, background: BackgroundTasks):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    runtime = get_video_generation_provider_v1("MINIMAX_H3_LOCAL").status()
    if not runtime.get("ready"):
        raise HTTPException(status_code=409, detail="本地 MiniMax H3 Runtime 尚未 READY")
    active = [task for task in list_project_tasks(project_id, limit=100) if task["status"] in ACTIVE_TASK_STATUSES]
    if active:
        existing = next((task for task in active if task["task_type"] == H3_QC_RETRY_TASK_TYPE), None)
        if existing is not None:
            return existing
        raise HTTPException(status_code=409, detail="当前已有后台重任务正在执行")
    task = create_task(
        project_id=project_id,
        task_type=H3_QC_RETRY_TASK_TYPE,
        title="重新生成 H3 镜头",
        progress_mode="indeterminate",
        deduplicate_active=False,
    )
    background.add_task(_run_manual_retry_task, task["id"], project_id, segment_id)
    return task


__all__ = ["H3_QC_RETRY_TASK_TYPE", "router"]
