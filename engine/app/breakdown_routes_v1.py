"""Breakdown-first Phase P1.4 的只读查询 API。

只暴露 Breakdown Run 历史、Episode Current Draft 和指定 Run 完整 Draft。
本模块不提供 create/publish/fail/stale 等写接口，也不运行任何推理。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_serializer_v1 import (
    get_breakdown_run,
    get_current_breakdown,
    list_breakdown_runs,
)

router = APIRouter(prefix="/api", tags=["breakdown"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


@router.get("/episodes/{episode_id}/breakdown-runs")
def api_list_breakdown_runs(episode_id: str) -> list[dict[str, Any]]:
    """列出 Episode 全部 Breakdown Run 历史，包含 FAILED/STALE。"""

    try:
        return list_breakdown_runs(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@router.get("/episodes/{episode_id}/breakdown-current")
def api_get_current_breakdown(episode_id: str) -> dict[str, Any] | None:
    """返回 Episode 当前 READY/READY_WITH_WARNINGS Draft；尚无 Current 时返回 null。"""

    try:
        return get_current_breakdown(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@router.get("/breakdown-runs/{run_id}")
def api_get_breakdown_run(run_id: str) -> dict[str, Any]:
    """读取指定 Run 的完整结构化 Draft；历史 FAILED/STALE Run 仍可查看。"""

    payload = get_breakdown_run(run_id)
    if payload is None:
        raise _not_found("Breakdown Run 不存在")
    return payload
