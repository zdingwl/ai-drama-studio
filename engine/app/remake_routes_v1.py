"""HTTP routes for project-level remake policy."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.app.remake_policy_v1 import (
    get_project_remake_policy,
    update_project_remake_policy,
)

router = APIRouter(prefix="/api", tags=["remake-policy"])


class ProjectRemakePolicyPatch(BaseModel):
    scene_policy: str | None = None
    generation_engine: str | None = None


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
