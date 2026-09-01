"""Product-facing SourceDramaSnapshot read APIs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_read_model_v1 import BreakdownReadModelError
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError
from engine.app.source_drama_snapshot_contract_v1 import (
    SourceDramaEpisodeSnapshotV1,
    SourceDramaProjectSnapshotV1,
)
from engine.app.source_drama_snapshot_v1 import (
    SourceDramaSnapshotError,
    load_episode_source_drama_snapshot_v1,
    load_project_source_drama_snapshot_v1,
)


router = APIRouter(prefix="/api", tags=["source-drama-snapshot"])


def _unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(
        status_code=409,
        detail="SourceDramaSnapshot 当前不可用，请先完成自动理解并处理阻塞性的镜头/资产问题。",
    )


@router.get(
    "/episodes/{episode_id}/source-drama-snapshot",
    response_model=SourceDramaEpisodeSnapshotV1 | None,
)
def api_get_episode_source_drama_snapshot(episode_id: str):
    try:
        return load_episode_source_drama_snapshot_v1(episode_id)
    except (
        LookupError,
        SourceDramaSnapshotError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/projects/{project_id}/source-drama-snapshot",
    response_model=SourceDramaProjectSnapshotV1,
)
def api_get_project_source_drama_snapshot(project_id: str):
    try:
        return load_project_source_drama_snapshot_v1(project_id)
    except (
        LookupError,
        SourceDramaSnapshotError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise _unavailable(exc) from exc


__all__ = [
    "api_get_episode_source_drama_snapshot",
    "api_get_project_source_drama_snapshot",
    "router",
]
