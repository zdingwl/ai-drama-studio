"""V2 拉片人工修正 + Revision API。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.app.playback_proxy_read_v2 import get_playback_proxy_read_only_v2
from engine.app.playback_proxy_v2 import PlaybackProxyError, ensure_playback_proxy
from engine.app.shot_editor_v2 import ShotEditError, adjust_boundary, merge_with_next, split_shot
from engine.app.shot_revision_read_v2 import list_shot_revisions_read_only_v2
from engine.app.shot_revision_v2 import (
    ensure_current_revision,
    get_revision_item_path,
    get_shot_revision,
    restore_shot_revision,
)

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
    """只读取已经准备好的整集有声播放代理，不在 GET 中生成/重封装文件。"""

    try:
        path = get_playback_proxy_read_only_v2(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except PlaybackProxyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Playback-Proxy": "v2",
        },
    )


@router.post("/episodes/{episode_id}/proxy/prepare")
def api_prepare_episode_proxy(episode_id: str) -> dict[str, str]:
    """显式准备/刷新播放代理；这是文件写操作，禁止由 GET 隐式触发。"""

    try:
        path = ensure_playback_proxy(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except PlaybackProxyError as exc:
        raise _bad_request(exc) from exc
    return {
        "episode_id": episode_id,
        "status": "READY",
        "proxy_url": f"/api/episodes/{episode_id}/proxy",
        "path": str(path),
    }


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
    """只列出现有 Shot Revision；旧项目缺 BASELINE 时返回空列表，不在 GET 中补写。"""

    try:
        return list_shot_revisions_read_only_v2(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@router.post("/episodes/{episode_id}/shot-revisions/ensure-baseline")
def api_ensure_shot_revision_baseline(episode_id: str):
    """显式为历史项目补建 BASELINE Revision；已有 Current 时幂等返回。"""

    try:
        return ensure_current_revision(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


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
