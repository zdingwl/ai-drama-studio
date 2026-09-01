"""R6 Dialogue Timing Engine / RemakeTimeline product APIs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.remake_timeline_contract_v1 import RemakeEpisodeTimelineV1, RemakeProjectTimelineV1
from engine.app.remake_timeline_v1 import (
    RemakeTimelineError,
    generate_remake_timeline_v1,
    get_remake_timeline_v1,
    update_remake_shot_timing_v1,
)
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError
from engine.app.target_dialogue_v1 import TargetDialogueError


router = APIRouter(tags=["remake-timeline"])


class ShotTimingEditRequest(BaseModel):
    strategy: str = Field(min_length=1, max_length=40)
    planned_duration_us: int = Field(ge=400_000)
    carry_over_shot_key: str | None = Field(default=None, max_length=220)
    reason: str | None = Field(default=None, max_length=2000)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (RemakeTimelineError, SourceDramaSnapshotError, TargetDialogueError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=409, detail=f"目标时间轴当前不可用：{exc}")


@router.post("/projects/{project_id}/remake-timeline/generate", response_model=RemakeProjectTimelineV1)
def api_generate_remake_timeline(project_id: str):
    try:
        return generate_remake_timeline_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/remake-timeline", response_model=RemakeProjectTimelineV1)
def api_get_remake_timeline(project_id: str):
    try:
        return get_remake_timeline_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.patch("/remake-timelines/{timeline_id}/shots/{shot_plan_id}", response_model=RemakeEpisodeTimelineV1)
def api_update_remake_shot_timing(timeline_id: str, shot_plan_id: str, payload: ShotTimingEditRequest):
    try:
        return update_remake_shot_timing_v1(
            timeline_id,
            shot_plan_id,
            **payload.model_dump(),
        )
    except Exception as exc:
        raise _error(exc) from exc


__all__ = ["router"]
