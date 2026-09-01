"""Read-only downstream APIs rooted in the current Breakdown read model.

P6 exposes the ordinary-user final Breakdown read model. P7.1 exposes an immutable
localization source package derived from that P6 truth. Neither route starts inference
or writes business state.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1
from engine.app.breakdown_read_model_v1 import BreakdownReadModelError, load_episode_breakdown_read_model_v1
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError
from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1
from engine.app.localization_source_v1 import LocalizationSourceError, load_episode_localization_source_v1


router = APIRouter(prefix="/api", tags=["breakdown-read-model"])


@router.get(
    "/episodes/{episode_id}/breakdown-read-model",
    response_model=BreakdownReadModelV1 | None,
)
def api_get_episode_breakdown_read_model(episode_id: str) -> dict[str, object] | None:
    """Return frozen Scene Timeline plus fail-closed Final Character/Scene/Prop display overlays."""

    try:
        return load_episode_breakdown_read_model_v1(episode_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="剧集不存在") from exc
    except (SceneTimelineResultError, SceneTimelineAssemblyError, BreakdownReadModelError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="拉片阅读结果当前不可用，请先确认本集拉片结果。") from exc


@router.get(
    "/episodes/{episode_id}/localization-source",
    response_model=LocalizationSourcePackageV1 | None,
    tags=["localization-source"],
)
def api_get_episode_localization_source(episode_id: str) -> dict[str, object] | None:
    """Return immutable current source facts for a future localization revision."""

    try:
        return load_episode_localization_source_v1(episode_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="剧集不存在") from exc
    except (
        LocalizationSourceError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail="本土化源资料当前不可用，请先确认拉片和最终资产结果。",
        ) from exc


__all__ = [
    "api_get_episode_breakdown_read_model",
    "api_get_episode_localization_source",
    "router",
]
