"""Stage 02 V5.1 缓存管理 API。

缓存操作只允许触碰 ``episode/cache/shot_v51``。Source、Shot Run、Current Revision、
Reference Clip 均不在删除范围内。拉片任务运行时禁止清缓存，避免正在读写的 artifact 被删除。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from engine.app.media_v51 import _expected_cache_manifest
from engine.app.shot_cache_v51 import cache_paths, cache_status, clear_cache
from engine.app.studio_v2 import episode_dir, get_episode_record, get_project, list_episode_records
from engine.app.task_progress_v2 import ACTIVE_TASK_STATUSES, list_project_tasks

router = APIRouter(prefix="/api", tags=["shot-cache-v51"])


def _episode_context(episode_id: str):
    episode = get_episode_record(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="剧集不存在")
    source = Path(episode.source_path)
    if not source.is_file():
        raise HTTPException(status_code=409, detail="原视频文件缺失，无法校验缓存")
    root = episode_dir(episode.project_id, episode.id)
    paths = cache_paths(root)
    expected = _expected_cache_manifest(episode, source)
    return episode, paths, expected


def _project_has_active_shot_task(project_id: str, episode_id: str | None = None) -> bool:
    for task in list_project_tasks(project_id, limit=100):
        if task.get("status") not in ACTIVE_TASK_STATUSES:
            continue
        task_type = task.get("task_type")
        if task_type == "BATCH_SHOTS":
            return True
        if task_type == "EPISODE_SHOTS" and (episode_id is None or task.get("episode_id") == episode_id):
            return True
    return False


@router.get("/episodes/{episode_id}/shot-cache")
def api_get_episode_shot_cache(episode_id: str) -> dict[str, Any]:
    episode, paths, expected = _episode_context(episode_id)
    payload = cache_status(paths, expected)
    payload.update({"episode_id": episode.id, "project_id": episode.project_id})
    return payload


@router.delete("/episodes/{episode_id}/shot-cache")
def api_clear_episode_shot_cache(
    episode_id: str,
    scope: str = Query(default="all", pattern="^(all|preprocess|flow|transvlm|transitions)$"),
) -> dict[str, Any]:
    episode, paths, expected = _episode_context(episode_id)
    if _project_has_active_shot_task(episode.project_id, episode.id):
        raise HTTPException(status_code=409, detail="该剧集或项目正在拉片，任务结束后再清除缓存")
    try:
        cleared = clear_cache(paths, scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = cache_status(paths, expected)
    return {
        "episode_id": episode.id,
        "project_id": episode.project_id,
        "cleared": cleared,
        "cache": payload,
    }


@router.delete("/projects/{project_id}/shot-cache")
def api_clear_project_shot_cache(
    project_id: str,
    scope: str = Query(default="all", pattern="^(all|preprocess|flow|transvlm|transitions)$"),
) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if _project_has_active_shot_task(project_id):
        raise HTTPException(status_code=409, detail="项目正在拉片，任务结束后再清除缓存")

    results: list[dict[str, Any]] = []
    total_bytes = 0
    for episode in list_episode_records(project_id):
        paths = cache_paths(episode_dir(project_id, episode.id))
        try:
            cleared = clear_cache(paths, scope)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        total_bytes += int(cleared["bytes_removed"])
        results.append({"episode_id": episode.id, "cleared": cleared})

    return {
        "project_id": project_id,
        "scope": scope,
        "episodes": len(results),
        "bytes_removed": total_bytes,
        "results": results,
    }
