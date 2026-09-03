"""HTTP routes for project-level remake policy and rebuilt project management."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from engine.app.project_management_v1 import (
    create_managed_project,
    get_managed_project,
    list_managed_projects,
    soft_delete_managed_project,
    update_managed_project,
)
from engine.app.remake_policy_v1 import (
    get_project_remake_policy,
    update_project_remake_policy,
)

router = APIRouter(prefix="/api", tags=["remake-policy"])


class ProjectRemakePolicyPatch(BaseModel):
    scene_policy: str | None = None
    generation_engine: str | None = None


RedrawRule = Literal["CHARACTER", "SCENE", "LANGUAGE"]


class ProjectManagementPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_language: str = Field(min_length=1, max_length=32)
    target_language: str = Field(min_length=1, max_length=32)
    target_region: str = Field(min_length=1, max_length=64)
    redraw_rules: list[RedrawRule] = Field(min_length=1)


@router.get("/project-management/projects")
def api_list_managed_projects():
    return list_managed_projects()


@router.post("/project-management/projects", status_code=status.HTTP_201_CREATED)
def api_create_managed_project(payload: ProjectManagementPayload):
    try:
        return create_managed_project(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project-management/projects/{project_id}")
def api_get_managed_project(project_id: str):
    try:
        return get_managed_project(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/project-management/projects/{project_id}")
def api_update_managed_project(project_id: str, payload: ProjectManagementPayload):
    try:
        return update_managed_project(project_id, **payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/project-management/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_managed_project(project_id: str) -> Response:
    try:
        soft_delete_managed_project(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/remake-policy")
def api_get_project_remake_policy(project_id: str):
    try:
        return get_project_remake_policy(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/projects/{project_id}/remake-policy")
def api_update_project_remake_policy(project_id: str, payload: ProjectRemakePolicyPatch):
    try:
        return update_project_remake_policy(
            project_id,
            scene_policy=payload.scene_policy,
            generation_engine=payload.generation_engine,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
