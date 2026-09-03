"""Lightweight read-only task summaries for project workspaces.

The historical task endpoint intentionally keeps the complete ``result`` payload for
backward compatibility and diagnostics.  Project pages poll task state frequently and
must not download multi-megabyte historical result blobs on every refresh, so this
read-only endpoint returns the same task metadata plus only the small per-episode result
fields needed by workspace status rendering.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from engine.app.studio_v2 import get_project
from engine.app.task_progress_v2 import list_project_tasks


router = APIRouter(tags=["task-summaries"])

_RESULT_ITEM_KEYS = (
    "episode_id",
    "status",
    "error",
    "shot_count",
    "run_id",
)
_RESULT_TOP_LEVEL_KEYS = (
    "mode",
    "episode_id",
    "status",
    "shot_count",
    "run_id",
    "profile_version",
)


def _safe_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _summarize_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    summary: dict[str, Any] = {}
    for key in _RESULT_TOP_LEVEL_KEYS:
        value = result.get(key)
        if key in result and _safe_scalar(value):
            summary[key] = value

    rows = result.get("results")
    if isinstance(rows, list):
        summarized_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = {
                key: row[key]
                for key in _RESULT_ITEM_KEYS
                if key in row and _safe_scalar(row[key])
            }
            if item:
                summarized_rows.append(item)
        summary["results"] = summarized_rows

    return summary or None


def _summarize_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        **task,
        "result": _summarize_result(task.get("result")),
    }


@router.get("/projects/{project_id}/task-summaries")
def api_list_project_task_summaries(
    project_id: str,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Return read-only task metadata suitable for frequently refreshed project pages."""

    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return [_summarize_task(task) for task in list_project_tasks(project_id, limit=limit)]


__all__ = ["api_list_project_task_summaries", "router"]
