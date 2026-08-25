"""V2 后台任务 API 与顺序执行器。

第一批接入：
- 单集 / 批量视频预处理；
- 单集 / 批量拉片；
- Project 级资产提取。

批量任务严格按 Episode.sort_order 顺序执行，不并行占用多个视频任务资源。
某一集失败时记录失败并继续后续剧集，最终 Task 标记 READY_WITH_WARNINGS，用户可单独重试失败集。
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from engine.app.content_analysis_v2 import run_content_analysis
from engine.app.media_v2 import detect_episode_shots, preprocess_episode
from engine.app.studio_v2 import get_episode, get_project, list_episode_records
from engine.app.task_progress_v2 import (
    ACTIVE_TASK_STATUSES,
    create_task,
    fail_task,
    finish_task,
    get_task,
    list_project_tasks,
    start_task,
    update_task,
)

router = APIRouter(prefix="/api", tags=["background-tasks"])

STAGE_LABELS = {
    "probe": "读取媒体信息",
    "proxy": "生成 Proxy",
    "audio": "提取 Audio",
    "frame_pts": "读取真实 PTS",
    "transnet": "TransNetV2 镜头检测",
    "boundaries": "整理 Shot 边界",
    "reference_clips": "生成 Reference Clip",
    "persist": "保存结果",
    "ready": "完成",
}


def _active_task(project_id: str, task_type: str, episode_id: str | None = None) -> dict[str, Any] | None:
    for task in list_project_tasks(project_id, limit=100):
        if (
            task["task_type"] == task_type
            and task.get("episode_id") == episode_id
            and task["status"] in ACTIVE_TASK_STATUSES
        ):
            return task
    return None


def _create_and_enqueue(
    *,
    background: BackgroundTasks,
    project_id: str,
    task_type: str,
    title: str,
    runner: Callable[..., None],
    runner_args: tuple[Any, ...],
    episode_id: str | None = None,
    progress_mode: str = "determinate",
    total_items: int | None = None,
) -> dict[str, Any]:
    """防重复创建并把同步 runner 放入 FastAPI 后台线程执行。"""

    existing = _active_task(project_id, task_type, episode_id)
    if existing is not None:
        return existing
    task = create_task(
        project_id=project_id,
        episode_id=episode_id,
        task_type=task_type,
        title=title,
        progress_mode=progress_mode,
        total_items=total_items,
        deduplicate_active=False,
    )
    background.add_task(runner, task["id"], *runner_args)
    return task


def _episode_name(episode: Any) -> str:
    return f"EP{int(episode.sort_order):02d} · {episode.title}"


def _stage_label(stage_key: str) -> str:
    return STAGE_LABELS.get(stage_key, stage_key)


def run_episode_preprocess_task(task_id: str, episode_id: str) -> None:
    try:
        episode = get_episode(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        start_task(task_id, stage_key="preprocess", stage_label="视频初始化", message="正在读取媒体并生成 Proxy / Audio")

        def report(percent: float, stage_key: str, message: str, current: int | None, total: int | None) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=percent,
                stage_key=stage_key,
                stage_label=_stage_label(stage_key),
                current_item=episode["title"],
                current_index=current or 1,
                total_items=total or 1,
                message=message,
            )

        result = preprocess_episode(episode_id, progress=report)
        finish_task(task_id, result=result, message="视频初始化完成")
    except Exception as exc:
        fail_task(task_id, exc)


def run_batch_preprocess_task(task_id: str, project_id: str) -> None:
    try:
        episodes = list_episode_records(project_id)
        total = len(episodes)
        if total == 0:
            raise ValueError("项目还没有剧集")
        start_task(task_id, stage_key="preprocess_batch", stage_label="批量视频初始化", message="按照剧集顺序逐集处理")
        results: list[dict[str, Any]] = []
        failures = 0
        for index, episode in enumerate(episodes, start=1):
            episode_name = _episode_name(episode)

            def report(percent: float, stage_key: str, message: str, current: int | None, inner_total: int | None, *, _index: int = index, _name: str = episode_name) -> None:
                overall = ((_index - 1) + percent / 100.0) / total * 100.0
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=overall,
                    current_item=_name,
                    current_index=_index,
                    total_items=total,
                    stage_key=stage_key,
                    stage_label=_stage_label(stage_key),
                    message=message,
                )

            update_task(
                task_id,
                progress_percent=((index - 1) / total) * 100,
                current_item=episode_name,
                current_index=index,
                total_items=total,
                stage_key="episode_preprocess",
                stage_label="视频初始化",
                message=f"正在处理 {episode_name}",
            )
            try:
                info = preprocess_episode(episode.id, progress=report)
                results.append({"episode_id": episode.id, "status": "READY", "media": info})
            except Exception as exc:
                failures += 1
                results.append({"episode_id": episode.id, "status": "FAILED", "error": str(exc)})
            update_task(
                task_id,
                progress_percent=(index / total) * 100,
                current_item=episode_name,
                current_index=index,
                total_items=total,
                message=f"已处理 {index} / {total} 集",
            )
        status = "READY_WITH_WARNINGS" if failures else "READY"
        message = f"批量初始化完成：{total - failures} 成功，{failures} 失败" if failures else f"批量初始化完成：{total} 集"
        finish_task(task_id, result={"mode": "sequential", "results": results}, message=message, status=status)
    except Exception as exc:
        fail_task(task_id, exc)


def run_episode_shots_task(task_id: str, episode_id: str) -> None:
    try:
        episode = get_episode(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        start_task(task_id, stage_key="shot_detection", stage_label="自动拉片", message="正在分析镜头边界并生成 Reference Clip")

        def report(percent: float, stage_key: str, message: str, current: int | None, total: int | None) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=percent,
                stage_key=stage_key,
                stage_label=_stage_label(stage_key),
                current_item=episode["title"],
                current_index=current if current is not None else 1,
                total_items=total if total is not None else 1,
                message=message,
            )

        shots = detect_episode_shots(episode_id, progress=report)
        finish_task(task_id, result={"episode_id": episode_id, "shot_count": len(shots)}, message=f"拉片完成：{len(shots)} Shots")
    except Exception as exc:
        fail_task(task_id, exc)


def run_batch_shots_task(task_id: str, project_id: str) -> None:
    try:
        episodes = list_episode_records(project_id)
        total = len(episodes)
        if total == 0:
            raise ValueError("项目还没有剧集")
        start_task(task_id, stage_key="shot_batch", stage_label="批量拉片", message="严格按照剧集顺序逐集拉片")
        results: list[dict[str, Any]] = []
        failures = 0
        for index, episode in enumerate(episodes, start=1):
            episode_name = _episode_name(episode)

            def report(percent: float, stage_key: str, message: str, current: int | None, inner_total: int | None, *, _index: int = index, _name: str = episode_name) -> None:
                overall = ((_index - 1) + percent / 100.0) / total * 100.0
                detail = message
                if current is not None and inner_total is not None and stage_key == "reference_clips":
                    detail = f"{_name} · Reference Clip {current} / {inner_total}"
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=overall,
                    current_item=_name,
                    current_index=_index,
                    total_items=total,
                    stage_key=stage_key,
                    stage_label=_stage_label(stage_key),
                    message=detail,
                )

            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=((index - 1) / total) * 100,
                current_item=episode_name,
                current_index=index,
                total_items=total,
                stage_key="episode_shots",
                stage_label="镜头检测 / Reference Clip",
                message=f"正在拉片 {episode_name}",
            )
            try:
                shots = detect_episode_shots(episode.id, progress=report)
                results.append({"episode_id": episode.id, "status": "READY", "shot_count": len(shots)})
            except Exception as exc:
                failures += 1
                results.append({"episode_id": episode.id, "status": "FAILED", "error": str(exc)})
            update_task(
                task_id,
                progress_percent=(index / total) * 100,
                current_item=episode_name,
                current_index=index,
                total_items=total,
                message=f"已完成 {index} / {total} 集",
            )
        status = "READY_WITH_WARNINGS" if failures else "READY"
        message = f"批量拉片完成：{total - failures} 成功，{failures} 失败" if failures else f"批量拉片完成：{total} 集"
        finish_task(task_id, result={"mode": "sequential", "results": results}, message=message, status=status)
    except Exception as exc:
        fail_task(task_id, exc)


def run_asset_extraction_task(task_id: str, project_id: str) -> None:
    """资产分析目前无法诚实计算模型内部百分比，因此使用阶段型 indeterminate 进度。"""

    try:
        start_task(task_id, stage_key="asset_prepare", stage_label="准备资产分析", message="正在读取 Final Shots 和模型状态")
        update_task(task_id, progress_mode="indeterminate", stage_key="asset_analysis", stage_label="人物 / 场景 / 道具分析", message="正在执行多镜头资产 Evidence 分析")
        result = run_content_analysis(project_id)
        finish_task(
            task_id,
            result={"run_id": result.get("id"), "profile_version": result.get("profile_version")},
            message="资产提取完成",
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.get("/projects/{project_id}/tasks")
def api_list_project_tasks(project_id: str, limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return list_project_tasks(project_id, limit=limit)


@router.get("/tasks/{task_id}")
def api_get_task(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="后台任务不存在")
    return task


@router.post("/episodes/{episode_id}/tasks/preprocess", status_code=202)
def api_start_episode_preprocess(episode_id: str, background: BackgroundTasks) -> dict[str, Any]:
    episode = get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="剧集不存在")
    return _create_and_enqueue(
        background=background,
        project_id=episode["project_id"],
        episode_id=episode_id,
        task_type="EPISODE_PREPROCESS",
        title=f"初始化 · {episode['title']}",
        runner=run_episode_preprocess_task,
        runner_args=(episode_id,),
        total_items=1,
    )


@router.post("/projects/{project_id}/tasks/preprocess-batch", status_code=202)
def api_start_batch_preprocess(project_id: str, background: BackgroundTasks) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    episodes = list_episode_records(project_id)
    return _create_and_enqueue(
        background=background,
        project_id=project_id,
        task_type="BATCH_PREPROCESS",
        title="批量视频初始化",
        runner=run_batch_preprocess_task,
        runner_args=(project_id,),
        total_items=len(episodes),
    )


@router.post("/episodes/{episode_id}/tasks/shots", status_code=202)
def api_start_episode_shots(episode_id: str, background: BackgroundTasks) -> dict[str, Any]:
    episode = get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="剧集不存在")
    return _create_and_enqueue(
        background=background,
        project_id=episode["project_id"],
        episode_id=episode_id,
        task_type="EPISODE_SHOTS",
        title=f"拉片 · {episode['title']}",
        runner=run_episode_shots_task,
        runner_args=(episode_id,),
        progress_mode="determinate",
        total_items=1,
    )


@router.post("/projects/{project_id}/tasks/shots-batch", status_code=202)
def api_start_batch_shots(project_id: str, background: BackgroundTasks) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    episodes = list_episode_records(project_id)
    return _create_and_enqueue(
        background=background,
        project_id=project_id,
        task_type="BATCH_SHOTS",
        title="批量拉片",
        runner=run_batch_shots_task,
        runner_args=(project_id,),
        total_items=len(episodes),
    )


@router.post("/projects/{project_id}/tasks/assets", status_code=202)
def api_start_assets(project_id: str, background: BackgroundTasks) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _create_and_enqueue(
        background=background,
        project_id=project_id,
        task_type="ASSET_EXTRACTION",
        title="资产提取",
        runner=run_asset_extraction_task,
        runner_args=(project_id,),
        progress_mode="indeterminate",
    )
