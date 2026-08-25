"""03 资产 Shot Review Matrix 批量 Binding API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.asset_batch_v4 import batch_set_shot_bindings
from engine.app.asset_workspace_v3 import AssetWorkspaceError

router = APIRouter(prefix="/api", tags=["asset-review-matrix"])


class BatchShotBindingsRequest(BaseModel):
    shot_ids: list[str] = Field(min_length=1)
    apply_characters: bool = False
    character_ids: list[str] = Field(default_factory=list)
    apply_scene: bool = False
    scene_id: str | None = None
    apply_props: bool = False
    prop_ids: list[str] = Field(default_factory=list)


@router.put("/projects/{project_id}/assets/bindings/batch")
def api_batch_set_shot_bindings(project_id: str, payload: BatchShotBindingsRequest):
    """一次提交多个 Shot 的部分 Binding，并只创建一个 MANUAL Revision。"""

    try:
        return batch_set_shot_bindings(
            project_id,
            payload.shot_ids,
            apply_characters=payload.apply_characters,
            character_ids=payload.character_ids,
            apply_scene=payload.apply_scene,
            scene_id=payload.scene_id,
            apply_props=payload.apply_props,
            prop_ids=payload.prop_ids,
        )
    except AssetWorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
