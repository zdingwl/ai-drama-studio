"""03 资产最终工作台 API。

所有写操作都修改 Final Asset / Shot Binding，并在同一事务中创建新的 MANUAL Revision。
AI Evidence 只读，不会被人工操作覆盖或删除。
Character V10.1 先采集 Person Evidence 再模型分类；只有确认的人物类别进入 Final Character。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from engine.app.asset_analysis_progress_v4 import run_content_analysis_with_progress
from engine.app.asset_final_gate_v10 import apply_analysis_to_assets
from engine.app.asset_semantics_p4_v1 import enrich_asset_run, semantic_model_status
from engine.app.asset_workspace_character_v101 import decorate_asset_workspace_character_evidence
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
from engine.app.review_issue_sync_v1 import sync_asset_review_issues
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


def _workspace_payload(workspace: dict[str, object]) -> dict[str, object]:
    """Expose V10.1 Character Evidence and keep its derived review attention state current.

    ReviewIssue is an attention/read-model cache, not Final Asset truth. Synchronizing it
    after decoration means existing projects are healed on their next workspace read:
    a Shot understood as containing people can no longer remain green merely because an
    older review-sync run did not know about character coverage.
    """

    payload = decorate_asset_workspace_character_evidence(workspace)
    project_id = str(payload.get("project_id") or "")
    if project_id:
        sync_asset_review_issues(project_id, payload)
    return payload


def _run_full_asset_task(task_id: str, project_id: str) -> None:
    """完整资产任务：V10.1 Person Evidence → 模型分类 → P4 Draft-guided Scene/Prop → Final Asset → Shot Binding。

    Character V10.1 负责人物实例采集、全局身份分类和已知身份 Track recovery；P4 只把当前
    Structured Draft 当作 Scene/Prop 搜索提示，再由资产侧 Qwen3-VL 对当前 Shot 图像重新验证。
    Draft 不是 Character/Scene/Prop Final Source of Truth。Qwen 未配置/失败时，人物 Final Asset
    仍可正常完成，任务以 READY_WITH_WARNINGS 结束。
    """

    try:
        start_task(
            task_id,
            stage_key="asset_prepare",
            stage_label="准备资产提取",
            message="正在读取 Final Shots 与人物 V10.1 Person Evidence / Model Classification",
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
        counts = dict(result.get("counts") or {})
        resolved_characters = int(counts.get("resolved_character_candidates") or 0)
        unresolved_evidence = int(counts.get("unresolved_character_candidates") or 0)

        vlm = semantic_model_status()
        semantic_result: dict[str, object] = {"status": "NOT_CONFIGURED", "shot_count": 0, "prop_count": 0}
        semantic_warning = False
        if vlm["ready"]:
            update_task(
                task_id,
                progress_mode="determinate",
                progress_percent=55,
                stage_key="asset_semantics",
                stage_label="Draft 引导场景 / 道具验证",
                current_item=None,
                current_index=0,
                total_items=None,
                message="正在读取当前 Structured Draft，并启动当前 Shot 图像验证",
            )

            def semantic_progress(current: int, total: int, message: str) -> None:
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=55 + (current / max(1, total)) * 35,
                    stage_key="asset_semantics",
                    stage_label="Draft 引导场景 / 道具验证",
                    current_item=f"Shot {current} / {total}",
                    current_index=current,
                    total_items=total,
                    message=message,
                )

            try:
                semantic_result = enrich_asset_run(run_id, project_id, progress=semantic_progress)
                semantic_warning = str(semantic_result.get("status") or "").upper() in {
                    "READY_WITH_WARNINGS", "FAILED", "NOT_CONFIGURED"
                }
            except Exception as exc:
                semantic_warning = True
                semantic_result = {"status": "FAILED", "error": str(exc), "shot_count": 0, "prop_count": 0}
                update_task(
                    task_id,
                    progress_mode="determinate",
                    progress_percent=90,
                    stage_key="asset_semantics",
                    stage_label="场景 / 道具验证失败",
                    current_item=None,
                    message="人物 V10.1 Evidence 已保留；Draft 不会被直接当作 Final 资产，可稍后重跑场景/道具验证",
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
            message=f"V10.1 只发布 {resolved_characters} 个确认人物类别；{unresolved_evidence} 个待归属 Evidence 不计入人物数",
        )
        workspace = apply_analysis_to_assets(project_id, run_id)
        manual_preserved = bool(workspace.get("stale"))
        warning = semantic_warning or manual_preserved or unresolved_evidence > 0
        if manual_preserved:
            message = "资产 Evidence 已更新；当前人工版本已保留，请按需采用新 Evidence"
        else:
            message = f"人物 V10.1：{resolved_characters} Final Character · {unresolved_evidence} 待归属 Evidence"
            if semantic_warning:
                message += "；场景/道具 Draft 引导验证存在提示"
        finish_task(
            task_id,
            result={
                "run_id": run_id,
                "profile_version": result.get("profile_version"),
                "resolved_characters": resolved_characters,
                "unresolved_character_evidence": unresolved_evidence,
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
        return _workspace_payload(get_asset_workspace(project_id))
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc


@router.get("/assets/models/status")
def api_asset_model_status():
    """场景/道具语义验证配置状态；人物 V10.1 模型由 /api/models/f05/status 提供。"""
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
        return _workspace_payload(apply_analysis_to_assets(project_id, analysis["id"], force=True))
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc


@router.put("/projects/{project_id}/assets/shots/{shot_id}/bindings")
def api_set_shot_bindings(project_id: str, shot_id: str, payload: ShotBindingsRequest):
    try:
        return _workspace_payload(set_shot_bindings(
            project_id,
            shot_id,
            character_ids=payload.character_ids,
            scene_id=payload.scene_id,
            prop_ids=payload.prop_ids,
        ))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets")
def api_create_asset(project_id: str, payload: AssetCreateRequest):
    try:
        return _workspace_payload(create_asset(project_id, payload.entity_type, payload.name, shot_id=payload.shot_id))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.patch("/projects/{project_id}/assets/{entity_type}/{entity_id}")
def api_rename_asset(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetRenameRequest):
    try:
        return _workspace_payload(rename_asset(project_id, entity_type, entity_id, payload.name))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.delete("/projects/{project_id}/assets/{entity_type}/{entity_id}")
def api_delete_asset(project_id: str, entity_type: AssetType, entity_id: str):
    try:
        return _workspace_payload(delete_asset(project_id, entity_type, entity_id))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets/merge")
def api_merge_assets(project_id: str, payload: AssetMergeRequest):
    try:
        return _workspace_payload(merge_assets(project_id, payload.entity_type, payload.entity_ids, target_id=payload.target_id))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/assets/{entity_type}/{entity_id}/split")
def api_split_asset(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetSplitRequest):
    if payload.entity_type != entity_type:
        raise _bad(ValueError("entity_type 不一致"))
    try:
        return _workspace_payload(split_asset(project_id, entity_type, entity_id, payload.shot_ids, new_name=payload.new_name))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.patch("/projects/{project_id}/assets/{entity_type}/{entity_id}/cover")
def api_set_asset_cover(project_id: str, entity_type: AssetType, entity_id: str, payload: AssetCoverRequest):
    try:
        return _workspace_payload(set_asset_cover(project_id, entity_type, entity_id, payload.cover_url))
    except AssetWorkspaceError as exc:
        raise _bad(exc) from exc


@router.post("/asset-revisions/{revision_id}/restore")
def api_restore_asset_revision(revision_id: str):
    try:
        return _workspace_payload(restore_asset_revision(revision_id))
    except (LookupError, AssetWorkspaceError) as exc:
        raise _bad(exc) from exc
