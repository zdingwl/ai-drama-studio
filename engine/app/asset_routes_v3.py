"""03 资产最终工作台 API。

所有写操作都修改 Final Asset / Shot Binding，并在同一事务中创建新的 MANUAL Revision。
AI Evidence 只读，不会被人工操作覆盖或删除。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.asset_semantics_v3 import semantic_model_status
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


@router.get("/projects/{project_id}/assets/workspace")
def api_asset_workspace(project_id: str):
    try:
        return get_asset_workspace(project_id)
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc


@router.get("/assets/models/status")
def api_asset_model_status():
    """Qwen3-VL 语义增强配置状态；YuNet/SFace 仍由 /api/models/f05/status 提供。"""
    return semantic_model_status()


@router.post("/projects/{project_id}/assets/apply-analysis")
def api_apply_analysis(project_id: str):
    """用户显式选择基于最新 AI Evidence 创建新的 AUTO Revision。"""
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
            project_id, shot_id,
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
