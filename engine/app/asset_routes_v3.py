"""03 资产最终工作台 API。

所有写操作都修改 Final Asset / Shot Binding，并在同一事务中创建新的 MANUAL Revision。
AI Evidence 只读，不会被人工操作覆盖或删除。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from engine.app.asset_analysis_progress_v4 import run_content_analysis_with_progress
from engine.app.asset_semantics_v3 import enrich_asset_run, semantic_model_status
from engine.app.asset_workspace_v3 import (
    AssetWorkspaceError,
    apply_analysis_to_assets,
    create_asset,
    delete_asset,
    get_asset_workspace,
    merge_assets,
    rename_asset,
    restore_asset_revision,
    set_asset_cover,
    set_shot_bindings,
    split_asset,
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

router = APIRouter(prefix="/api", tags=["asset-workspace"])
AssetType = Literal["character", "scene", "prop"]


class ShotBindingsRequest(BaseModel):
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    prop_ids: list[str] = Field(default_factory=list)


class AssetCreateRequest(BaseModel):
    entity_type: AssetType
    name: str = Field(min_length=1, max_length=200)
    shot_id: str | None = None


class AssetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AssetMergeRequest(BaseModel):
    entity_type: AssetType
    entity_ids: list[str] = Field(min_length=2)
    target_id: str | None = None


class AssetSplitRequest(BaseModel):
    entity_type: AssetType
    shot_ids: list[str] = Field(min_length=1)
    new_name: str | None = Field(default=None, max_length=200)


class AssetCoverRequest(BaseModel):
    cover_url: str = Field(min_length=1)


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _run_full_asset_task(task_id: str, project_id: str) -> None:
    """完整资产任务：基础 Evidence → optional VLM → Final Asset → Shot Binding。

    基础人物 V4 已经能按真实 Shot 报进度，这里把它映射到总任务前 55%。
    Qwen3-VL 是语义增强而不是人物身份 Source of Truth，所以它未配置或临时失败时，
    人物与基础连续场景仍然必须形成 Final Asset；任务以 READY_WITH_WARNINGS 完成，而不是整批失败。
    """

    try:
        start_task(
            task_id,
            stage_key="asset_prepare",
            stage_label="准备资产提取",
            message="正在读取 Final Shots 与人物 V4 模型",
        )
        update_task(
            task_id,
            progress_mode="determinate",
            progress_percent=0,
            stage_key="asset_prepare",
            stage_label="准备资产提取",
            message="正在准备人物 / 场景 Evidence",
        )

        def evidence_progress(
            percent: float,
            stage_key: str,
            stage_label: str,
            current_item: str | None,
            current_index: int | None,
            total_items: int | None,
            message: str,
        ) -> None:
            # 基础 Evidence 占完整资产任务前 55%。人物 V4 内部的 percent 来自实际 Shot 进度，
            # 不是前端估算；场景/持久化阶段也会持续更新心跳。
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=max(0.0, min(55.0, percent * 0.55)),
                stage_key=stage_key,
                stage_label=stage_label,
                current_item=current_item,
                current_index=current_index,
                total_items=total_items,
                message=message,
            )

        result = run_content_analysis_with_progress(project_id, progress=evidence_progress)
        run_id = str(result["id"])

        vlm = semantic_model_status()
        semantic_result: dict[str, object] = {"status": "NOT_CONFIGURED", "shot_count": 0, "prop_count": 0}
        semantic_warning = False
        if vlm["ready"]:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=55,
                stage_key="asset_semantics",
                stage_label="Qwen3-VL 场景 / 道具",
                current_item=None,
                current_index=0,
                total_items=None,
                message="正在启动多模态语义分析",
            )

            def semantic_progress(current: int, total: int, message: str) -> None:
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=55 + (current / max(1, total)) * 35,
                    stage_key="asset_semantics",
                    stage_label="Qwen3-VL 场景 / 道具",
                    current_item=f"Shot {current} / {total}",
                    current_index=current,
                    total_items=total,
                    message=message,
                )

            try:
                semantic_result = enrich_asset_run(run_id, project_id, progress=semantic_progress)
            except Exception as exc:
                semantic_warning = True
                semantic_result = {"status": "FAILED", "error": str(exc), "shot_count": 0, "prop_count": 0}
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=90,
                    stage_key="asset_semantics",
                    stage_label="Qwen3-VL 增强失败",
                    current_item=None,
                    message="已保留人物与基础场景 Evidence；场景语义/道具可人工维护或稍后重跑",
                )
        else:
            semantic_warning = True
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=90,
                stage_key="asset_semantics",
                stage_label="场景 / 道具语义",
                current_item=None,
                message="Qwen3-VL 未配置：保留基础场景 Evidence，道具可人工维护",
            )

        update_task(
            task_id,
            progress_mode="determinate",
            progress_percent=94,
            stage_key="asset_finalize",
            stage_label="形成 Final Asset",
            current_item=None,
            current_index=None,
            total_items=None,
            message="正在建立人物 / 场景 / 道具与 Shot Binding",
        )
        workspace = apply_analysis_to_assets(project_id, run_id)
        manual_preserved = bool(workspace.get("stale"))
        warning = semantic_warning or manual_preserved
        if manual_preserved:
            message = "资产 Evidence 已更新；当前人工版本已保留，请按需采用新 Evidence"
        elif semantic_warning:
            message = "人物 / 基础场景资产已完成；Qwen3-VL 语义增强未完成"
        else:
            message = "资产提取与 Shot Binding 完成"
        finish_task(
            task_id,
            result={
                "run_id": run_id,
                "profile_version": result.get("profile_version"),
                "semantic": semantic_result,
                "asset_revision": (workspace.get("revision") or {}).get("revision"),
                "manual_preserved": manual_preserved,
            },
            message=message,
            status="READY_WITH_WARNINGS" if warning else "READY",
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.get("/projects/{project_id}/assets/workspace")
def api_asset_workspace(project_id: str):
    try:
        return get_asset_workspace(project_id)
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc


@router.get("/assets/models/status")
def api_asset_model_status():
    """Qwen3-VL 语义增强配置状态；人物 V4 模型由 /api/models/f05/status 提供。"""
    return semantic_model_status()


@router.post("/projects/{project_id}/assets/tasks/extract", status_code=202)
def api_start_full_asset_task(project_id: str, background: BackgroundTasks):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    for task in list_project_tasks(project_id, limit=100):
        if task["task_type"] == "ASSET_EXTRACTION_V3" and task["status"] in ACTIVE_TASK_STATUSES:
            return task
    task = create_task(
        project_id=project_id,
        episode_id=None,
        task_type="ASSET_EXTRACTION_V3",
        title="资产提取",
        progress_mode="determinate",
        deduplicate_active=False,
    )
    background.add_task(_run_full_asset_task, task["id"], project_id)
    return task


@router.post("/projects/{project_id}/assets/apply-analysis")
def api_apply_analysis(project_id: str):
    """用户显式选择：基于最新 AI Evidence 创建新的 AUTO Revision。"""
    workspace = get_asset_workspace(project_id, auto_bootstrap=False)
    analysis = workspace.get("analysis")
    if not analysis:
        raise _bad(ValueError("当前没有可用资产 AI Run"))
    try:
        return apply_analysis_to_assets(project_id, analysis["id"], force=True)
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc


@router.put("/projects/{project_id}/assets/shots/{shot_id}/bindings")
def api_set_shot_bindings(project_id: str, shot_id: str, payload: ShotBindingsRequest):
    try:
        return set_shot_bindings(
            project_id,
            shot_id,
            character_ids=payload.character_ids,
            scene_id=payload.scene_id,
            prop_ids=payload.prop_ids,
        )
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets")
def api_create_asset(project_id: str, payload: AssetCreateRequest):
    try:
        return create_asset(project_id, payload.entity_type, payload.name, shot_id=payload.shot_id)
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.patch("/projects/{project_id}/assets/{entity_type}/{entity_id}")
def api_rename_asset(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetRenameRequest):
    try:
        return rename_asset(project_id, entity_type, entity_id, payload.name)
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.delete("/projects/{project_id}/assets/{entity_type}/{entity_id}")
def api_delete_asset(project_id: str, entity_type: AssetType, entity_id: str):
    try:
        return delete_asset(project_id, entity_type, entity_id)
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets/merge")
def api_merge_assets(project_id: str, payload: AssetMergeRequest):
    try:
        return merge_assets(project_id, payload.entity_type, payload.entity_ids, target_id=payload.target_id)
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets/{entity_type}/{entity_id}/split")
def api_split_asset(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetSplitRequest):
    if payload.entity_type != entity_type:
        raise _bad(ValueError("entity_type 不一致"))
    try:
        return split_asset(project_id, entity_type, entity_id, payload.shot_ids, new_name=payload.new_name)
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.patch("/projects/{project_id}/assets/{entity_type}/{entity_id}/cover")
def api_set_asset_cover(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetCoverRequest):
    try:
        return set_asset_cover(project_id, entity_type, entity_id, payload.cover_url)
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/asset-revisions/{revision_id}/restore")
def api_restore_asset_revision(revision_id: str):
    try:
        return restore_asset_revision(revision_id)
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc
