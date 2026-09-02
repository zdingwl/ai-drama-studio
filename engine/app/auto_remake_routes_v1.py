"""One-click automatic analysis and downstream output task entrypoints."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine.app.auto_output_v1 import AUTO_OUTPUT_TASK_TYPE, run_auto_output_task
from engine.app.auto_remake_prepare_v1 import run_auto_remake_prepare_task
from engine.app.studio_v2 import get_project, list_episode_records
from engine.app.task_progress_v2 import ACTIVE_TASK_STATUSES, create_task, list_project_tasks

router = APIRouter(prefix="/api", tags=["auto-remake"])

AUTO_TASK_TYPE = "AUTO_REMAKE_PREP_V1"
HEAVY_TASK_TYPES = {
    AUTO_TASK_TYPE,
    AUTO_OUTPUT_TASK_TYPE,
    "H3_GENERATE_READY_V1",
    "H3_QC_RETRY_V1",
    "POSTPRODUCTION_V1",
    "EPISODE_SHOTS",
    "BATCH_SHOTS",
    "EPISODE_BREAKDOWN_P2",
    "BATCH_BREAKDOWN_P2",
    "ASSET_EXTRACTION_V3",
    "ASSET_EXTRACTION",
}


def _project_episodes(project_id: str):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    episodes = list_episode_records(project_id)
    if not episodes:
        raise HTTPException(status_code=400, detail="项目还没有剧集")
    return episodes


def _active_heavy_tasks(project_id: str) -> list[dict]:
    return [
        task for task in list_project_tasks(project_id, limit=100)
        if task["status"] in ACTIVE_TASK_STATUSES and task["task_type"] in HEAVY_TASK_TYPES
    ]


@router.post("/projects/{project_id}/tasks/auto-remake-prepare", status_code=202)
def api_start_auto_remake_prepare(project_id: str, background: BackgroundTasks):
    episodes = _project_episodes(project_id)
    active = _active_heavy_tasks(project_id)
    existing = next((task for task in active if task["task_type"] == AUTO_TASK_TYPE), None)
    if existing is not None:
        return existing
    if active:
        raise HTTPException(status_code=409, detail="当前已有本地重任务正在执行，请先等待当前任务结束")

    task = create_task(
        project_id=project_id,
        episode_id=None,
        task_type=AUTO_TASK_TYPE,
        title="自动理解原短剧",
        progress_mode="determinate",
        total_items=len(episodes),
        deduplicate_active=False,
    )
    background.add_task(run_auto_remake_prepare_task, task["id"], project_id)
    return task


@router.post("/projects/{project_id}/tasks/auto-output", status_code=202)
def api_start_auto_output(project_id: str, background: BackgroundTasks):
    """Continue from current source truth to final output without rerunning analysis."""

    episodes = _project_episodes(project_id)
    active = _active_heavy_tasks(project_id)
    existing = next((task for task in active if task["task_type"] == AUTO_OUTPUT_TASK_TYPE), None)
    if existing is not None:
        return existing
    if active:
        raise HTTPException(status_code=409, detail="当前已有本地重任务正在执行，请先等待当前任务结束")

    task = create_task(
        project_id=project_id,
        episode_id=None,
        task_type=AUTO_OUTPUT_TASK_TYPE,
        title="自动生成最终成片",
        progress_mode="determinate",
        total_items=len(episodes),
        deduplicate_active=False,
    )
    background.add_task(run_auto_output_task, task["id"], project_id)
    return task


__all__ = ["AUTO_OUTPUT_TASK_TYPE", "AUTO_TASK_TYPE", "HEAVY_TASK_TYPES", "router"]
