"""03 资产最终工作台 API。

所有写操作都修改 Final Asset / Shot Binding，并在同一事务中创建新的 MANUAL Revision。
AI Evidence 只读，不会被人工操作覆盖或删除。
Character V9D 只有 Confirmed Person Gallery 才能进入 Final Character；UNRESOLVED 只保留 Evidence。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from engine.app.asset_analysis_progress_v4 import run_content_analysis_with_progress
from engine.app.asset_final_gate_v9 import apply_analysis_to_assets
from engine.app.asset_semantics_v3 import enrich_asset_run, semantic_model_status
from engine.app.asset_workspace_v3 import (
    AssetWorkspaceError,
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
    """后台执行完整资产提取，并把 AI Evidence 安全应用到 Final Asset。"""

    start_task(task_id)

    def report(
        percent: float,
        stage_key: str,
        stage_label: str,
        current_item: str | None,
        current_index: int | None,
        total_items: int | None,
        message: str,
    ) -> None:
        update_task(
            task_id,
            percent=percent,
            stage_key=stage_key,
            stage_label=stage_label,
            current_item=current_item,
            current_index=current_index,
            total_items=total_items,
            message=message,
        )

    try:
        run = run_content_analysis_with_progress(project_id, progress=report)
        run_id = str(run.get("id") or "")
        if not run_id:
            raise AssetWorkspaceError("资产分析 Run 创建失败")

        update_task(
            task_id,
            percent=96.0,
            stage_key="asset_semantics",
            stage_label="资产语义整理",
            message="正在整理人物 / 场景 / 道具语义信息",
        )
        enrich_asset_run(run_id, project_id)

        update_task(
            task_id,
            percent=98.0,
            stage_key="asset_apply",
            stage_label="应用最新资产 Evidence",
            message="正在根据 V9D Confirmed Person Gallery Final Gate 生成 Final Asset Revision",
        )
        workspace = apply_analysis_to_assets(project_id, run_id)
        finish_task(
            task_id,
            result={
                "run_id": run_id,
                "revision": (workspace.get("revision") or {}).get("revision") if isinstance(workspace, dict) else None,
            },
            message="资产提取完成",
        )
    except Exception as exc:
        fail_task(task_id, str(exc))


@router.get("/projects/{project_id}/assets/workspace")
def get_workspace(project_id: str):
    try:
        return get_asset_workspace(project_id)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.get("/assets/models/status")
def get_asset_semantic_model_status():
    return semantic_model_status()


@router.post("/projects/{project_id}/assets/tasks/extract")
def start_full_asset_extraction(project_id: str, background_tasks: BackgroundTasks):
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    active = [
        item for item in list_project_tasks(project_id, limit=20)
        if item.get("task_type") == "ASSET_EXTRACTION" and item.get("status") in ACTIVE_TASK_STATUSES
    ]
    if active:
        return active[0]

    task = create_task(
        project_id=project_id,
        task_type="ASSET_EXTRACTION",
        stage_key="asset_prepare",
        stage_label="准备资产 Evidence",
        message="资产提取任务已进入队列",
    )
    background_tasks.add_task(_run_full_asset_task, task["id"], project_id)
    return task


@router.post("/projects/{project_id}/assets/apply-analysis")
def apply_latest_analysis(project_id: str):
    try:
        workspace = get_asset_workspace(project_id)
        analysis = workspace.get("analysis") if isinstance(workspace, dict) else None
        if not isinstance(analysis, dict) or not analysis.get("id"):
            raise AssetWorkspaceError("当前没有可采用的资产分析结果")
        return apply_analysis_to_assets(project_id, str(analysis["id"]), force=True)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.put("/projects/{project_id}/assets/shots/{shot_id}/bindings")
def update_shot_bindings(project_id: str, shot_id: str, payload: ShotBindingsRequest):
    try:
        return set_shot_bindings(
            project_id,
            shot_id,
            character_ids=payload.character_ids,
            scene_id=payload.scene_id,
            prop_ids=payload.prop_ids,
        )
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets")
def create_final_asset(project_id: str, payload: AssetCreateRequest):
    try:
        return create_asset(project_id, payload.entity_type, payload.name, shot_id=payload.shot_id)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.patch("/projects/{project_id}/assets/{entity_type}/{entity_id}")
def rename_final_asset(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetRenameRequest):
    try:
        return rename_asset(project_id, entity_type, entity_id, payload.name)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.delete("/projects/{project_id}/assets/{entity_type}/{entity_id}")
def delete_final_asset(project_id: str, entity_type: AssetType, entity_id: str):
    try:
        return delete_asset(project_id, entity_type, entity_id)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets/merge")
def merge_final_assets(project_id: str, payload: AssetMergeRequest):
    try:
        return merge_assets(project_id, payload.entity_type, payload.entity_ids, target_id=payload.target_id)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets/{entity_type}/{entity_id}/split")
def split_final_asset(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetSplitRequest):
    if payload.entity_type != entity_type:
        raise HTTPException(status_code=400, detail="entity_type 不一致")
    try:
        return split_asset(
            project_id,
            entity_type,
            entity_id,
            payload.shot_ids,
            new_name=payload.new_name,
        )
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.patch("/projects/{project_id}/assets/{entity_type}/{entity_id}/cover")
def update_final_asset_cover(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetCoverRequest):
    try:
        return set_asset_cover(project_id, entity_type, entity_id, payload.cover_url)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/asset-revisions/{revision_id}/restore")
def restore_revision(revision_id: str):
    try:
        return restore_asset_revision(revision_id)
    except (AssetWorkspaceError, LookupError) as exc:
        raise _bad(exc) from exc
