"""G2.5 ordinary-user Scene Timeline read API.

These endpoints expose only the strict ``scene-timeline-v1`` result contract. They do not execute
ASR/OCR/VLM/Qwen, do not publish Breakdown Runs, and do not return engineering provenance.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.breakdown_scene_timeline_result_v1 import (
    SceneTimelineResultError,
    build_scene_timeline_result_v1,
)
from engine.app.breakdown_serializer_v1 import get_breakdown_run, get_current_breakdown


router = APIRouter(prefix="/api", tags=["scene-timeline"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _result_unavailable() -> HTTPException:
    return HTTPException(status_code=409, detail="Scene Timeline 结果当前不可用，请先完成本集拉片。")


def _build_result(draft: dict[str, object]) -> dict[str, object]:
    try:
        return build_scene_timeline_result_v1(draft)
    except (SceneTimelineResultError, SceneTimelineAssemblyError, ValueError) as exc:
        raise _result_unavailable() from exc


@router.get(
    "/episodes/{episode_id}/scene-timeline",
    response_model=SceneTimelinePayloadV1 | None,
)
def api_get_episode_scene_timeline(episode_id: str) -> dict[str, object] | None:
    """Return the current completed Scene Timeline for one Episode, or null when none exists yet."""

    try:
        draft = get_current_breakdown(episode_id)
    except LookupError as exc:
        raise _not_found("剧集不存在") from exc
    if draft is None:
        return None
    return _build_result(draft)


@router.get(
    "/breakdown-runs/{run_id}/scene-timeline",
    response_model=SceneTimelinePayloadV1,
)
def api_get_run_scene_timeline(run_id: str) -> dict[str, object]:
    """Return one explicit historical completed Run through the same ordinary-user contract."""

    draft = get_breakdown_run(run_id)
    if draft is None:
        raise _not_found("Breakdown Run 不存在")
    return _build_result(draft)


__all__ = [
    "api_get_episode_scene_timeline",
    "api_get_run_scene_timeline",
    "router",
]
