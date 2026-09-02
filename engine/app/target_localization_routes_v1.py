"""Target-side remake APIs rooted under the shared /api prefix."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.generation_segment_routes_v1 import router as generation_segment_router
from engine.app.h3_generation_routes_v1 import router as h3_generation_router
from engine.app.remake_timeline_routes_v1 import router as remake_timeline_router
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError
from engine.app.target_dialogue_routes_v1 import router as target_dialogue_router
from engine.app.target_localization_contract_v1 import (
    SceneLocalizationMappingV1,
    TargetCharacterV1,
    TargetLocalizationBundleV1,
)
from engine.app.target_localization_runtime_guard_v1 import (
    TargetLocalizationRuntimeUnavailable,
    require_target_localization_runtime_v1,
    validate_target_localization_generation_v1,
)
from engine.app.target_localization_v1 import (
    TargetLocalizationError,
    delete_scene_localization_v1,
    delete_target_character_v1,
    generate_target_localization_v1,
    get_target_localization_v1,
    update_scene_localization_v1,
    update_target_character_v1,
)


router = APIRouter(prefix="/api", tags=["target-localization"])
router.include_router(target_dialogue_router)
router.include_router(remake_timeline_router)
router.include_router(generation_segment_router)
router.include_router(h3_generation_router)


class TargetCharacterEditRequest(BaseModel):
    target_name: str = Field(min_length=1, max_length=200)
    appearance_profile: str = Field(min_length=1, max_length=8000)
    generation_prompt: str = Field(min_length=1, max_length=8000)


class SceneLocalizationEditRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=24)
    target_label: str | None = Field(default=None, max_length=200)
    target_description: str | None = Field(default=None, max_length=8000)
    reason: str | None = Field(default=None, max_length=2000)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TargetLocalizationRuntimeUnavailable, TargetLocalizationError)):
        # Model/runtime execution failures are infrastructure state, not a business conflict and
        # must not be hidden behind the generic "localization unavailable" message.
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, SourceDramaSnapshotError):
        return HTTPException(status_code=409, detail="SourceDramaSnapshot 当前不可用")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail="目标人物/场景本土化当前不可用")


@router.post("/projects/{project_id}/target-localization/generate", response_model=TargetLocalizationBundleV1)
def api_generate_target_localization(project_id: str):
    try:
        require_target_localization_runtime_v1(project_id)
        bundle = generate_target_localization_v1(project_id)
        return validate_target_localization_generation_v1(project_id, bundle)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/target-localization", response_model=TargetLocalizationBundleV1)
def api_get_target_localization(project_id: str):
    try:
        return get_target_localization_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.patch("/target-characters/{target_character_id}", response_model=TargetCharacterV1)
def api_update_target_character(target_character_id: str, payload: TargetCharacterEditRequest):
    try:
        return update_target_character_v1(target_character_id, **payload.model_dump())
    except Exception as exc:
        raise _error(exc) from exc


@router.delete("/target-characters/{target_character_id}", status_code=204)
def api_delete_target_character(target_character_id: str) -> None:
    try:
        delete_target_character_v1(target_character_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.patch("/scene-localization-mappings/{mapping_id}", response_model=SceneLocalizationMappingV1)
def api_update_scene_localization(mapping_id: str, payload: SceneLocalizationEditRequest):
    try:
        return update_scene_localization_v1(mapping_id, **payload.model_dump())
    except Exception as exc:
        raise _error(exc) from exc


@router.delete("/scene-localization-mappings/{mapping_id}", status_code=204)
def api_delete_scene_localization(mapping_id: str) -> None:
    try:
        delete_scene_localization_v1(mapping_id)
    except Exception as exc:
        raise _error(exc) from exc


__all__ = ["router"]
