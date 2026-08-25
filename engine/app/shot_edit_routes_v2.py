"""V2 拉片人工修正 API。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.shot_editor_v2 import ShotEditError, adjust_boundary, merge_with_next, split_shot

router = APIRouter(prefix="/api", tags=["shot-editing"])


class BoundaryEditRequest(BaseModel):
    """移动当前 Shot start/end 所对应的公共边界。"""

    side: Literal["start", "end"]
    source_time_us: int = Field(ge=0)


class SplitShotRequest(BaseModel):
    """按 Source Domain 微秒时间拆分当前 Shot。"""

    source_time_us: int = Field(ge=0)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.patch("/shots/{shot_id}/boundary")
def api_adjust_shot_boundary(shot_id: str, payload: BoundaryEditRequest):
    try:
        return adjust_boundary(shot_id=shot_id, side=payload.side, source_time_us=payload.source_time_us)
    except ShotEditError as exc:
        raise _bad_request(exc) from exc


@router.post("/shots/{shot_id}/split")
def api_split_shot(shot_id: str, payload: SplitShotRequest):
    try:
        return split_shot(shot_id=shot_id, source_time_us=payload.source_time_us)
    except ShotEditError as exc:
        raise _bad_request(exc) from exc


@router.post("/shots/{shot_id}/merge-next")
def api_merge_shot_with_next(shot_id: str):
    try:
        return merge_with_next(shot_id=shot_id)
    except ShotEditError as exc:
        raise _bad_request(exc) from exc
