"""V2 拉片人工修正 + Revision API。"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.app.shot_editor_v2 import ShotEditError, adjust_boundary, merge_with_next, split_shot
from engine.app.shot_revision_v2 import (
    get_revision_item_path,
    get_shot_revision,
    list_shot_revisions,
    restore_shot_revision,
)
from engine.app.studio_v2 import get_episode_record

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


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


@router.get("/episodes/{episode_id}/proxy")
def api_episode_proxy(episode_id: str) -> FileResponse:
    """给拉片工作台播放整集 Proxy。

    为什么存在：人工移动 Cut / 拆分时需要在完整 Source 时间轴上自由拖动播放头，
    不能只播放当前 Shot 的 Reference Clip。
    """

    episode = get_episode_record(episode_id)
    if episode is None:
        raise _not_found("剧集不存在")
    preprocess = episode.preprocess
    if preprocess is None or preprocess.status != "READY" or not preprocess.proxy_path:
        raise _bad_request(ValueError("当前剧集的分析视频尚未准备完成"))
    path = Path(preprocess.proxy_path)
    if not path.is_file():
        raise _not_found("分析视频不存在")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


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


@router.get("/episodes/{episode_id}/shot-revisions")
def api_list_shot_revisions(episode_id: str):
    """列出某一集全部 Shot Revision；第一次读取旧项目会自动补 BASELINE R1。"""

    try:
        return list_shot_revisions(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@router.get("/shot-revisions/{revision_id}")
def api_get_shot_revision(revision_id: str):
    payload = get_shot_revision(revision_id)
    if payload is None:
        raise _not_found("Shot Revision 不存在")
    return payload


@router.post("/shot-revisions/{revision_id}/restore")
def api_restore_shot_revision(revision_id: str):
    """恢复历史版本会创建新的 RESTORE Revision，不改写被恢复的历史记录。"""

    try:
        return restore_shot_revision(revision_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/shot-revision-items/{item_id}/reference")
def api_revision_reference(item_id: str) -> FileResponse:
    path = get_revision_item_path(item_id, "reference")
    if path is None or not path.is_file():
        raise _not_found("历史 Reference Clip 不存在")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/shot-revision-items/{item_id}/thumbnail")
def api_revision_thumbnail(item_id: str) -> FileResponse:
    path = get_revision_item_path(item_id, "thumbnail")
    if path is None or not path.is_file():
        raise _not_found("历史镜头缩略图不存在")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)
