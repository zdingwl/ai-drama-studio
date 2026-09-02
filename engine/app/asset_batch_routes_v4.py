"""03 资产 Shot Review Matrix 批量 Binding API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.asset_batch_v4 import batch_set_shot_bindings
from engine.app.asset_workspace_character_v101 import decorate_asset_workspace_character_evidence
from engine.app.asset_workspace_v3 import AssetWorkspaceError
from engine.app.review_issue_sync_v1 import sync_asset_review_issues

router = APIRouter(prefix="/api", tags=["asset-review-matrix"])


class BatchShotBindingsRequest(BaseModel):
    shot_ids: list[str] = Field(min_length=1)
    apply_characters: bool = False
    character_ids: list[str] = Field(default_factory=list)
    apply_scene: bool = False
    scene_id: str | None = None
    apply_props: bool = False
    prop_ids: list[str] = Field(default_factory=list)


def _after_explicit_batch_write(project_id: str, workspace: dict) -> dict:
    """Refresh derived ReviewIssue only after the user has written real binding facts."""

    payload = decorate_asset_workspace_character_evidence(workspace)
    sync_asset_review_issues(project_id, payload)
    return payload


@router.put("/projects/{project_id}/assets/bindings/batch")
def api_batch_set_shot_bindings(project_id: str, payload: BatchShotBindingsRequest):
    """一次提交多个 Shot 的部分 Binding，并只创建一个 MANUAL Revision。"""

    try:
        workspace = batch_set_shot_bindings(
            project_id,
            payload.shot_ids,
            apply_characters=payload.apply_characters,
            character_ids=payload.character_ids,
            apply_scene=payload.apply_scene,
            scene_id=payload.scene_id,
            apply_props=payload.apply_props,
            prop_ids=payload.prop_ids,
        )
        return _after_explicit_batch_write(project_id, workspace)
    except AssetWorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
