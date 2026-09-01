"""Downstream APIs rooted in current Breakdown/localization truth.

P6 exposes the ordinary-user Breakdown read model. P7.1 exposes immutable localization
source facts. P7.2 owns only revisioned target-side copy and review state; it never
accepts source_text from write requests.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1
from engine.app.breakdown_read_model_v1 import BreakdownReadModelError, load_episode_breakdown_read_model_v1
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError
from engine.app.localization_draft_contract_v1 import (
    LocalizationDraftEditV1,
    LocalizationDraftStatus,
    LocalizationDraftViewV1,
    LocalizationRevisionSummaryV1,
)
from engine.app.localization_draft_v1 import (
    LocalizationDraftConflictError,
    LocalizationDraftError,
    LocalizationDraftStaleError,
    get_current_localization_draft,
    get_localization_revision,
    list_localization_revisions,
)
from engine.app.localization_draft_workflow_v1 import (
    create_localization_draft_safe,
    edit_localization_draft_safe,
    rebase_localization_draft_safe,
    set_localization_draft_status_safe,
)
from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1
from engine.app.localization_source_v1 import LocalizationSourceError, load_episode_localization_source_v1


router = APIRouter(prefix="/api", tags=["breakdown-read-model"])


class LocalizationDraftCreateRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class LocalizationDraftEditRequest(BaseModel):
    base_revision_id: str = Field(min_length=1, max_length=64)
    entries: list[LocalizationDraftEditV1] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=1000)


class LocalizationDraftStatusRequest(BaseModel):
    base_revision_id: str = Field(min_length=1, max_length=64)
    status: LocalizationDraftStatus
    note: str | None = Field(default=None, max_length=1000)


class LocalizationDraftRebaseRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


def _localization_write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail="剧集或本土化版本不存在")
    if isinstance(exc, (LocalizationDraftConflictError, LocalizationDraftStaleError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LocalizationDraftError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail="本土化源资料当前不可用，请先确认拉片和最终资产结果。")


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


@router.get(
    "/episodes/{episode_id}/localization-draft",
    response_model=LocalizationDraftViewV1 | None,
    tags=["localization-draft"],
)
def api_get_current_localization_draft(episode_id: str):
    try:
        return get_current_localization_draft(episode_id)
    except Exception as exc:
        raise _localization_write_error(exc) from exc


@router.post(
    "/episodes/{episode_id}/localization-draft",
    response_model=LocalizationDraftViewV1,
    tags=["localization-draft"],
)
def api_create_localization_draft(episode_id: str, payload: LocalizationDraftCreateRequest):
    try:
        return create_localization_draft_safe(episode_id, note=payload.note)
    except Exception as exc:
        raise _localization_write_error(exc) from exc


@router.patch(
    "/episodes/{episode_id}/localization-draft",
    response_model=LocalizationDraftViewV1,
    tags=["localization-draft"],
)
def api_edit_localization_draft(episode_id: str, payload: LocalizationDraftEditRequest):
    try:
        return edit_localization_draft_safe(
            episode_id,
            base_revision_id=payload.base_revision_id,
            entries=payload.entries,
            note=payload.note,
        )
    except Exception as exc:
        raise _localization_write_error(exc) from exc


@router.post(
    "/episodes/{episode_id}/localization-draft/status",
    response_model=LocalizationDraftViewV1,
    tags=["localization-draft"],
)
def api_set_localization_draft_status(episode_id: str, payload: LocalizationDraftStatusRequest):
    try:
        return set_localization_draft_status_safe(
            episode_id,
            base_revision_id=payload.base_revision_id,
            status=payload.status,
            note=payload.note,
        )
    except Exception as exc:
        raise _localization_write_error(exc) from exc


@router.post(
    "/episodes/{episode_id}/localization-draft/rebase",
    response_model=LocalizationDraftViewV1,
    tags=["localization-draft"],
)
def api_rebase_localization_draft(episode_id: str, payload: LocalizationDraftRebaseRequest):
    try:
        return rebase_localization_draft_safe(episode_id, note=payload.note)
    except Exception as exc:
        raise _localization_write_error(exc) from exc


@router.get(
    "/episodes/{episode_id}/localization-revisions",
    response_model=list[LocalizationRevisionSummaryV1],
    tags=["localization-draft"],
)
def api_list_localization_revisions(episode_id: str):
    try:
        return list_localization_revisions(episode_id)
    except Exception as exc:
        raise _localization_write_error(exc) from exc


@router.get(
    "/localization-revisions/{revision_id}",
    response_model=LocalizationDraftViewV1,
    tags=["localization-draft"],
)
def api_get_localization_revision(revision_id: str):
    try:
        return get_localization_revision(revision_id)
    except Exception as exc:
        raise _localization_write_error(exc) from exc


__all__ = [
    "api_create_localization_draft",
    "api_edit_localization_draft",
    "api_get_current_localization_draft",
    "api_get_episode_breakdown_read_model",
    "api_get_episode_localization_source",
    "api_get_localization_revision",
    "api_list_localization_revisions",
    "api_rebase_localization_draft",
    "api_set_localization_draft_status",
    "router",
]
