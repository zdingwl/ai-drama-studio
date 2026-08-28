"""Breakdown read API plus P2 production/acceptance task entrypoints.

P1 read endpoints remain history-safe. P2 write endpoints only enqueue background execution of the
formal ASR -> OCR -> VLM -> Fusion pipeline; they do not expose lower-level provider writes.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from engine.app.breakdown_p2_acceptance_v1 import (
    build_acceptance_report,
    collect_p2_runtime_preflight,
    write_acceptance_report,
)
from engine.app.breakdown_p2_pipeline_v1 import run_episode_breakdown_p2
from engine.app.breakdown_serializer_v1 import (
    get_breakdown_run,
    get_current_breakdown,
    list_breakdown_runs,
)
from engine.app.studio_v2 import get_episode, get_project, list_episode_records
from engine.app.task_progress_v2 import (
    ACTIVE_TASK_STATUSES,
    create_task,
    fail_task,
    finish_task,
    list_project_tasks,
    start_task,
    update_task,
)

router = APIRouter(prefix="/api", tags=["breakdown"])

BREAKDOWN_TASK_TYPE = "EPISODE_BREAKDOWN_P2"
BREAKDOWN_BATCH_TASK_TYPE = "BATCH_BREAKDOWN_P2"
_STAGE_LABELS = {
    "breakdown_prepare": "准备 AI 拉片",
    "breakdown_asr": "对白识别",
    "breakdown_ocr": "画面文字识别",
    "breakdown_vlm": "视频内容理解",
    "breakdown_fusion": "多模态融合",
    "breakdown_ready": "AI 拉片完成",
}


class P2AcceptanceRequest(BaseModel):
    human_review: dict[str, Any] | None = None
    include_preflight: bool = True
    output_path: str | None = None


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _active_task(project_id: str, task_type: str, episode_id: str | None) -> dict[str, Any] | None:
    for task in list_project_tasks(project_id, limit=100):
        if (
            task["task_type"] == task_type
            and task.get("episode_id") == episode_id
            and task["status"] in ACTIVE_TASK_STATUSES
        ):
            return task
    return None


def _enqueue(
    background: BackgroundTasks,
    *,
    project_id: str,
    episode_id: str | None,
    task_type: str,
    title: str,
    runner: Any,
    runner_args: tuple[Any, ...],
    total_items: int | None,
) -> dict[str, Any]:
    existing = _active_task(project_id, task_type, episode_id)
    if existing is not None:
        return existing
    task = create_task(
        project_id=project_id,
        episode_id=episode_id,
        task_type=task_type,
        title=title,
        progress_mode="determinate",
        total_items=total_items,
        deduplicate_active=False,
    )
    background.add_task(runner, task["id"], *runner_args)
    return task


def _stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage)


def run_episode_breakdown_task(task_id: str, episode_id: str) -> None:
    try:
        episode = get_episode(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        start_task(
            task_id,
            stage_key="breakdown_prepare",
            stage_label=_stage_label("breakdown_prepare"),
            message="正在冻结 ShotRevision 并准备 ASR / OCR / VLM",
        )

        def report(percent: float, stage: str, message: str) -> None:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=percent,
                stage_key=stage,
                stage_label=_stage_label(stage),
                current_item=episode["title"],
                current_index=1,
                total_items=1,
                message=message,
            )

        run = run_episode_breakdown_p2(episode_id, progress=report)
        finish_task(
            task_id,
            result={"run_id": run.id, "episode_id": episode_id, "status": run.status},
            message="匿名结构化 AI 拉片完成",
            status="READY_WITH_WARNINGS" if run.status == "READY_WITH_WARNINGS" else "READY",
        )
    except Exception as exc:
        fail_task(task_id, exc)


def run_batch_breakdown_task(task_id: str, project_id: str) -> None:
    try:
        episodes = list_episode_records(project_id)
        total = len(episodes)
        if total == 0:
            raise ValueError("项目还没有剧集")
        start_task(
            task_id,
            stage_key="breakdown_prepare",
            stage_label="批量 AI 拉片",
            message="严格按照 Episode.sort_order 顺序逐集执行",
        )
        results: list[dict[str, Any]] = []
        failures = 0
        warned = 0
        for index, episode_record in enumerate(episodes, start=1):
            episode = get_episode(episode_record.id)
            if episode is None:
                failures += 1
                results.append({"episode_id": episode_record.id, "status": "FAILED", "error": "剧集不存在"})
                continue
            episode_name = f"EP{int(episode['sort_order']):02d} · {episode['title']}"

            def report(percent: float, stage: str, message: str, *, _index: int = index, _name: str = episode_name) -> None:
                overall = ((_index - 1) + max(0.0, min(100.0, percent)) / 100.0) / total * 100.0
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=overall,
                    stage_key=stage,
                    stage_label=_stage_label(stage),
                    current_item=_name,
                    current_index=_index,
                    total_items=total,
                    message=message,
                )

            try:
                run = run_episode_breakdown_p2(episode["id"], progress=report)
                if run.status == "READY_WITH_WARNINGS":
                    warned += 1
                results.append({"episode_id": episode["id"], "run_id": run.id, "status": run.status})
            except Exception as exc:
                failures += 1
                results.append({"episode_id": episode["id"], "status": "FAILED", "error": str(exc)})

            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=index / total * 100.0,
                current_item=episode_name,
                current_index=index,
                total_items=total,
                message=f"已完成 {index} / {total} 集",
            )

        task_status = "READY_WITH_WARNINGS" if failures or warned else "READY"
        finish_task(
            task_id,
            result={"mode": "sequential", "results": results},
            message=f"批量 AI 拉片完成：{total - failures} 成功，{failures} 失败",
            status=task_status,
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.get("/episodes/{episode_id}/breakdown-runs")
def api_list_breakdown_runs(episode_id: str) -> list[dict[str, Any]]:
    """列出 Episode 全部 Breakdown Run 历史，包含 FAILED/STALE。"""

    try:
        return list_breakdown_runs(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@router.get("/episodes/{episode_id}/breakdown-current")
def api_get_current_breakdown(episode_id: str) -> dict[str, Any] | None:
    """返回 Episode 当前 READY/READY_WITH_WARNINGS Draft；尚无 Current 时返回 null。"""

    try:
        return get_current_breakdown(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@router.get("/breakdown-runs/{run_id}")
def api_get_breakdown_run(run_id: str) -> dict[str, Any]:
    """读取指定 Run 的完整结构化 Draft；历史 FAILED/STALE Run 仍可查看。"""

    payload = get_breakdown_run(run_id)
    if payload is None:
        raise _not_found("Breakdown Run 不存在")
    return payload


@router.post("/episodes/{episode_id}/tasks/breakdown", status_code=202)
def api_start_episode_breakdown(episode_id: str, background: BackgroundTasks) -> dict[str, Any]:
    """后台执行单集完整 P2：ASR -> OCR -> VLM -> Fusion -> publish。"""

    episode = get_episode(episode_id)
    if episode is None:
        raise _not_found("剧集不存在")
    return _enqueue(
        background,
        project_id=episode["project_id"],
        episode_id=episode_id,
        task_type=BREAKDOWN_TASK_TYPE,
        title=f"AI 拉片 · {episode['title']}",
        runner=run_episode_breakdown_task,
        runner_args=(episode_id,),
        total_items=1,
    )


@router.post("/projects/{project_id}/tasks/breakdown-batch", status_code=202)
def api_start_batch_breakdown(project_id: str, background: BackgroundTasks) -> dict[str, Any]:
    """严格按 Episode.sort_order 顺序执行完整 P2；绝不并行轰炸模型/GPU。"""

    if get_project(project_id) is None:
        raise _not_found("项目不存在")
    episodes = list_episode_records(project_id)
    return _enqueue(
        background,
        project_id=project_id,
        episode_id=None,
        task_type=BREAKDOWN_BATCH_TASK_TYPE,
        title="批量 AI 拉片",
        runner=run_batch_breakdown_task,
        runner_args=(project_id,),
        total_items=len(episodes),
    )


@router.get("/breakdown/p2/runtime-preflight")
def api_p2_runtime_preflight() -> dict[str, Any]:
    """检查本机 P2 runtime/model 路径；不下载、不推理、不修改 Run。"""

    return collect_p2_runtime_preflight()


@router.post("/breakdown-runs/{run_id}/p2-acceptance")
def api_build_p2_acceptance(run_id: str, payload: P2AcceptanceRequest) -> dict[str, Any]:
    """为已完成 Run 生成 P2.6 真实素材验收报告；不会隐式重跑模型。"""

    try:
        report = build_acceptance_report(
            run_id,
            human_review=payload.human_review,
            include_preflight=payload.include_preflight,
        )
        path = write_acceptance_report(report, output_path=payload.output_path)
        return {"report_path": str(path), "report": report}
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
