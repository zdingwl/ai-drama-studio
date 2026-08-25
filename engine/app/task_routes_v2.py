"""V2 后台任务 API 与顺序执行器。

正式用户 Workflow：
- 拉片任务会自动检查当前 Episode 的预处理状态；
- 未准备时先生成 Proxy / Audio / Media Info，再继续 Shot Detection；
- 已准备时直接复用，不重复执行预处理；
- 批量拉片严格按 Episode.sort_order 顺序逐集完成“初始化 + 拉片”，不并行处理多个视频；
- Project 级资产提取继续使用同一套 Task Progress。

单独 preprocess Task 路由暂时保留给兼容、测试和故障排查，不再作为正式 UI 阶段。
某一集批量处理失败时记录失败并继续后续剧集，最终 Task 标记 READY_WITH_WARNINGS。
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

# 拉片 Workflow 中预处理约占前 25%，Shot Detection / Reference Clip 占后 75%。
# 这里只是把已有内部真实进度映射到统一 Task 百分比，不伪造模型内部进度。
SHOT_WORKFLOW_PREPROCESS_WEIGHT = 0.25

STAGE_LABELS = {
    "probe": "读取媒体信息",
    "proxy": "准备分析视频",
    "audio": "提取音频",
    "reuse_preprocess": "复用分析资产",
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
    """创建并入队后台任务。

    输入：Project / Episode 作用域、Task 类型、runner。
    输出：持久化 Task DTO。
    为什么：正式页面只发一次“开始任务”请求，真正耗时工作在后台执行；重复点击返回已有活动任务。
    """

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
    if isinstance(episode, dict):
        return f"EP{int(episode['sort_order']):02d} · {episode['title']}"
    return f"EP{int(episode.sort_order):02d} · {episode.title}"


def _stage_label(stage_key: str) -> str:
    return STAGE_LABELS.get(stage_key, stage_key)


def _needs_preprocess(episode: dict[str, Any]) -> bool:
    """判断拉片前是否需要自动准备媒体分析资产。

    当前 V2 以 preprocess_status=READY 代表当前 Episode 已有可复用 Proxy / Audio。
    后续 Source Versioning 接入后，这里再增加 source_version / source_sha 依赖校验。
    """

    return episode.get("preprocess_status") != "READY"


def run_episode_preprocess_task(task_id: str, episode_id: str) -> None:
    """兼容/诊断用单集预处理任务；正式 UI 不再把它作为独立生产步骤。"""

    try:
        episode = get_episode(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        start_task(task_id, stage_key="probe", stage_label="读取媒体信息", message="正在准备 Proxy / Audio / Media Info")

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
    """兼容/诊断用批量预处理任务；正式批量拉片会自行完成这一阶段。"""

    try:
        episodes = list_episode_records(project_id)
        total = len(episodes)
        if total == 0:
            raise ValueError("项目还没有剧集")
        start_task(task_id, stage_key="probe", stage_label="批量视频初始化", message="按照剧集顺序逐集处理")
        results: list[dict[str, Any]] = []
        failures = 0
        for index, episode in enumerate(episodes, start=1):
            episode_name = _episode_name(episode)

            def report(
                percent: float,
                stage_key: str,
                message: str,
                current: int | None,
                inner_total: int | None,
                *,
                _index: int = index,
                _name: str = episode_name,
            ) -> None:
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
                stage_key="probe",
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
    """执行单集“拉片”Workflow：必要时自动预处理，再执行 Shot Detection。

    用户不需要知道 F03；如果 Proxy / Audio 已经 READY 就直接复用。
    """

    try:
        episode = get_episode(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        start_task(task_id, stage_key="probe", stage_label="准备拉片", message="正在检查视频分析资产")

        if _needs_preprocess(episode):
            def preprocess_report(
                percent: float,
                stage_key: str,
                message: str,
                current: int | None,
                total: int | None,
            ) -> None:
                workflow_percent = percent * SHOT_WORKFLOW_PREPROCESS_WEIGHT
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=workflow_percent,
                    stage_key=stage_key,
                    stage_label=_stage_label(stage_key),
                    current_item=episode["title"],
                    current_index=1,
                    total_items=1,
                    message=message,
                )

            preprocess_episode(episode_id, progress=preprocess_report)
        else:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=SHOT_WORKFLOW_PREPROCESS_WEIGHT * 100,
                stage_key="reuse_preprocess",
                stage_label=_stage_label("reuse_preprocess"),
                current_item=episode["title"],
                current_index=1,
                total_items=1,
                message="Proxy / Audio 已就绪，直接复用",
            )

        def shot_report(
            percent: float,
            stage_key: str,
            message: str,
            current: int | None,
            total: int | None,
        ) -> None:
            workflow_percent = (
                SHOT_WORKFLOW_PREPROCESS_WEIGHT
                + (percent / 100.0) * (1.0 - SHOT_WORKFLOW_PREPROCESS_WEIGHT)
            ) * 100.0
            detail = message
            if current is not None and total is not None and stage_key == "reference_clips":
                detail = f"Reference Clip {current} / {total}"
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=workflow_percent,
                stage_key=stage_key,
                stage_label=_stage_label(stage_key),
                current_item=episode["title"],
                current_index=1,
                total_items=1,
                message=detail,
            )

        shots = detect_episode_shots(episode_id, progress=shot_report)
        finish_task(task_id, result={"episode_id": episode_id, "shot_count": len(shots)}, message=f"拉片完成：{len(shots)} Shots")
    except Exception as exc:
        fail_task(task_id, exc)


def run_batch_shots_task(task_id: str, project_id: str) -> None:
    """按剧集顺序执行批量拉片；每一集内部先自动确保预处理，再完成拉片。"""

    try:
        episodes = list_episode_records(project_id)
        total = len(episodes)
        if total == 0:
            raise ValueError("项目还没有剧集")
        start_task(task_id, stage_key="probe", stage_label="批量拉片", message="严格按照剧集顺序逐集处理")
        results: list[dict[str, Any]] = []
        failures = 0

        for index, episode_record in enumerate(episodes, start=1):
            episode = get_episode(episode_record.id)
            if episode is None:
                failures += 1
                results.append({"episode_id": episode_record.id, "status": "FAILED", "error": "剧集不存在"})
                continue

            episode_name = _episode_name(episode)

            def update_episode_progress(
                local_percent: float,
                stage_key: str,
                message: str,
                current: int | None = None,
                inner_total: int | None = None,
                *,
                _index: int = index,
                _name: str = episode_name,
            ) -> None:
                overall = ((_index - 1) + max(0.0, min(100.0, local_percent)) / 100.0) / total * 100.0
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

            update_episode_progress(0, "probe", f"正在准备 {episode_name}")

            try:
                if _needs_preprocess(episode):
                    def preprocess_report(
                        percent: float,
                        stage_key: str,
                        message: str,
                        current: int | None,
                        inner_total: int | None,
                    ) -> None:
                        update_episode_progress(
                            percent * SHOT_WORKFLOW_PREPROCESS_WEIGHT,
                            stage_key,
                            message,
                            current,
                            inner_total,
                        )

                    preprocess_episode(episode["id"], progress=preprocess_report)
                else:
                    update_episode_progress(
                        SHOT_WORKFLOW_PREPROCESS_WEIGHT * 100,
                        "reuse_preprocess",
                        "Proxy / Audio 已就绪，直接复用",
                    )

                def shot_report(
                    percent: float,
                    stage_key: str,
                    message: str,
                    current: int | None,
                    inner_total: int | None,
                ) -> None:
                    local_percent = (
                        SHOT_WORKFLOW_PREPROCESS_WEIGHT
                        + (percent / 100.0) * (1.0 - SHOT_WORKFLOW_PREPROCESS_WEIGHT)
                    ) * 100.0
                    update_episode_progress(local_percent, stage_key, message, current, inner_total)

                shots = detect_episode_shots(episode["id"], progress=shot_report)
                results.append({"episode_id": episode["id"], "status": "READY", "shot_count": len(shots)})
            except Exception as exc:
                failures += 1
                results.append({"episode_id": episode["id"], "status": "FAILED", "error": str(exc)})

            update_episode_progress(100, "ready", f"已完成 {index} / {total} 集")

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


# 兼容/诊断接口：正式 UI 不再单独暴露“预处理”阶段。
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