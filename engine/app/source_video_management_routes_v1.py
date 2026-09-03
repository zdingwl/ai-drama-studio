"""项目入口页的原短剧视频管理 HTTP API。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from engine.app.source_video_management_v1 import (
    SourceVideoManagementError,
    import_project_source_video,
    list_project_source_videos,
    replace_episode_source_video,
)

router = APIRouter(tags=["source-video-management"])


def _business_error(exc: SourceVideoManagementError) -> HTTPException:
    status_code = status.HTTP_409_CONFLICT if exc.code in {
        "PROJECT_TASK_ACTIVE",
        "VIDEO_REPLACE_CONFLICT",
    } else status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/projects/{project_id}/source-videos")
def api_list_project_source_videos(project_id: str) -> list[dict[str, Any]]:
    """只读返回页面视频列表；不会创建 Task、预处理或重新计算。"""

    try:
        return list_project_source_videos(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/source-videos",
    status_code=status.HTTP_201_CREATED,
)
def api_import_project_source_video(
    project_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """页面正式单文件上传入口；批量上传由前端逐文件顺序调用，便于独立重试。"""

    try:
        return import_project_source_video(project_id, file)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoManagementError as exc:
        raise _business_error(exc) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/episodes/{episode_id}/source")
def api_replace_episode_source_video(
    episode_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """替换单集原片；保留 Episode ID/排序，旧派生结果转为非 Current/STALE。"""

    try:
        return replace_episode_source_video(episode_id, file)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoManagementError as exc:
        raise _business_error(exc) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["router"]
