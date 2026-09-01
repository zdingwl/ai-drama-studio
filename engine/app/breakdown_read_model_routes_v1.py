"""P6 ordinary-user final Breakdown read-model API.

This route composes frozen G2 + frozen P5. It never starts inference and never writes business state.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1
from engine.app.breakdown_read_model_v1 import BreakdownReadModelError, load_episode_breakdown_read_model_v1
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError


router = APIRouter(prefix="/api", tags=["breakdown-read-model"])


@router.get(
    "/episodes/{episode_id}/breakdown-read-model",
    response_model=BreakdownReadModelV1 | None,
)
def api_get_episode_breakdown_read_model(episode_id: str) -> dict[str, object] | None:
    """Return current Scene Timeline plus fail-closed Final Character display overlay."""

    try:
        return load_episode_breakdown_read_model_v1(episode_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="剧集不存在") from exc
    except (SceneTimelineResultError, SceneTimelineAssemblyError, BreakdownReadModelError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="拉片阅读结果当前不可用，请先确认本集拉片结果。") from exc


__all__ = ["api_get_episode_breakdown_read_model", "router"]
