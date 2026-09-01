"""R7 GenerationSegment + local H3 runtime APIs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.generation_segment_contract_v1 import GenerationSegmentPlanV1
from engine.app.generation_segment_v1 import (
    GenerationSegmentError,
    compile_generation_segments_v1,
    get_generation_segments_v1,
)
from engine.app.h3_runtime_v1 import h3_runtime_status_v1
from engine.app.remake_timeline_v1 import RemakeTimelineError
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError
from engine.app.target_dialogue_v1 import TargetDialogueError
from engine.app.target_localization_v1 import TargetLocalizationError


router = APIRouter(prefix="/api", tags=["generation-segments"])


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(
        exc,
        (
            GenerationSegmentError,
            RemakeTimelineError,
            SourceDramaSnapshotError,
            TargetDialogueError,
            TargetLocalizationError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=409, detail=f"GenerationSegment 当前不可用：{exc}")


@router.post("/projects/{project_id}/generation-segments/compile", response_model=GenerationSegmentPlanV1)
def api_compile_generation_segments(project_id: str):
    try:
        return compile_generation_segments_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/generation-segments", response_model=GenerationSegmentPlanV1)
def api_get_generation_segments(project_id: str):
    try:
        return get_generation_segments_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/h3/runtime")
def api_h3_runtime_status():
    return h3_runtime_status_v1()


__all__ = ["router"]
