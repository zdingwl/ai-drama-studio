"""G2.5 ordinary-user Scene Timeline read/write API.

GET remains pure-read and never executes ASR/OCR/VLM/Qwen. AI Breakdown evidence stays immutable;
explicit PATCH writes only a ShotRevision-scoped manual override artifact and then returns the
projected current Scene Timeline.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.breakdown_manual_override_v1 import (
    BreakdownManualOverrideError,
    persist_shot_manual_edit_v1,
)
from engine.app.breakdown_scene_timeline_assembler_v1 import (
    SceneTimelineAssemblyError,
    assemble_scene_timeline_v1,
)
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.breakdown_scene_timeline_result_v1 import (
    SceneTimelineResultError,
    build_scene_timeline_result_v1,
)
from engine.app.breakdown_serializer_v1 import get_breakdown_run, get_current_breakdown


router = APIRouter(prefix="/api", tags=["scene-timeline"])


class SceneManualEditRequest(BaseModel):
    location: str | None = Field(default=None, max_length=255)
    interior_exterior: str | None = Field(default=None, max_length=64)
    time_of_day: str | None = Field(default=None, max_length=64)
    environment: str | None = Field(default=None, max_length=4000)


class DialogueManualEditRequest(BaseModel):
    index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=8000)


class ShotManualEditRequest(BaseModel):
    summary: str | None = Field(default=None, max_length=4000)
    visual_description: str | None = Field(default=None, max_length=8000)
    narrative_function: str | None = Field(default=None, max_length=4000)
    performance_text: str | None = Field(default=None, max_length=8000)
    shot_type: str | None = Field(default=None, max_length=128)
    composition: str | None = Field(default=None, max_length=1000)
    camera_motion: str | None = Field(default=None, max_length=256)
    scene: SceneManualEditRequest | None = None
    dialogues: list[DialogueManualEditRequest] | None = Field(default=None, max_length=200)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _result_unavailable() -> HTTPException:
    return HTTPException(status_code=409, detail="Scene Timeline 结果当前不可用，请先完成本集拉片。")


def _build_result(draft: dict[str, object]) -> dict[str, object]:
    try:
        return build_scene_timeline_result_v1(draft)
    except (SceneTimelineResultError, SceneTimelineAssemblyError, ValueError) as exc:
        raise _result_unavailable() from exc


def _build_immutable_anchor(draft: dict[str, object]) -> dict[str, object]:
    """Build frozen G2.2 facts only; PATCH anchors must never use already-overridden user text."""

    try:
        return assemble_scene_timeline_v1(draft)
    except (SceneTimelineAssemblyError, ValueError) as exc:
        raise _result_unavailable() from exc


@router.get(
    "/episodes/{episode_id}/scene-timeline",
    response_model=SceneTimelinePayloadV1 | None,
)
def api_get_episode_scene_timeline(episode_id: str) -> dict[str, object] | None:
    """Return current Scene Timeline plus compatible explicit manual edits."""

    try:
        draft = get_current_breakdown(episode_id)
    except LookupError as exc:
        raise _not_found("剧集不存在") from exc
    if draft is None:
        return None
    return _build_result(draft)


@router.patch(
    "/episodes/{episode_id}/scene-timeline/shots/{shot_ordinal}",
    response_model=SceneTimelinePayloadV1,
)
def api_edit_episode_scene_timeline_shot(
    episode_id: str,
    shot_ordinal: int,
    payload: ShotManualEditRequest,
) -> dict[str, object]:
    """Persist explicit user corrections without mutating the AI BreakdownRun/Draft."""

    try:
        draft = get_current_breakdown(episode_id)
    except LookupError as exc:
        raise _not_found("剧集不存在") from exc
    if draft is None:
        raise _result_unavailable()

    edits = payload.model_dump(exclude_unset=True)
    if not edits:
        raise HTTPException(status_code=400, detail="没有需要保存的修改")

    anchor = _build_immutable_anchor(draft)
    try:
        persist_shot_manual_edit_v1(
            draft,
            anchor,
            shot_ordinal=shot_ordinal,
            edits=edits,
        )
        return _build_result(draft)
    except LookupError as exc:
        raise _not_found("分镜不存在或当前没有拉片结果") from exc
    except (BreakdownManualOverrideError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/breakdown-runs/{run_id}/scene-timeline",
    response_model=SceneTimelinePayloadV1,
)
def api_get_run_scene_timeline(run_id: str) -> dict[str, object]:
    """Return one explicit historical completed Run through the ordinary-user contract."""

    draft = get_breakdown_run(run_id)
    if draft is None:
        raise _not_found("Breakdown Run 不存在")
    return _build_result(draft)


__all__ = [
    "api_edit_episode_scene_timeline_shot",
    "api_get_episode_scene_timeline",
    "api_get_run_scene_timeline",
    "router",
]
