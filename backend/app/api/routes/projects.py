from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.artifacts.schemas import ArtifactGraphRead, ArtifactNodeRead
from app.artifacts.service import get_artifact_graph, list_artifacts
from app.db.session import get_db
from app.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.projects.service import create_project, get_project, list_projects, update_project
from app.skills.plan import (
    ProjectExecutionPlan,
    compile_and_persist_execution_plan,
    get_current_execution_plan,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project_route(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectRead.model_validate(create_project(db, payload))


@router.get("", response_model=list[ProjectRead])
def list_projects_route(db: Session = Depends(get_db)) -> list[ProjectRead]:
    return [ProjectRead.model_validate(project) for project in list_projects(db)]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project_route(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectRead.model_validate(get_project(db, project_id))


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project_route(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    return ProjectRead.model_validate(update_project(db, project_id, payload))


@router.get("/{project_id}/plan", response_model=ProjectExecutionPlan)
def get_project_plan_route(project_id: str, db: Session = Depends(get_db)) -> ProjectExecutionPlan:
    return get_current_execution_plan(db, project_id)


@router.post("/{project_id}/commands/compile-plan", response_model=ProjectExecutionPlan)
def compile_project_plan_route(project_id: str, db: Session = Depends(get_db)) -> ProjectExecutionPlan:
    return compile_and_persist_execution_plan(db, project_id)


@router.get("/{project_id}/artifacts", response_model=list[ArtifactNodeRead])
def list_project_artifacts_route(project_id: str, db: Session = Depends(get_db)) -> list[ArtifactNodeRead]:
    return [ArtifactNodeRead.model_validate(item) for item in list_artifacts(db, project_id)]


@router.get("/{project_id}/artifact-graph", response_model=ArtifactGraphRead)
def get_project_artifact_graph_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> ArtifactGraphRead:
    return get_artifact_graph(db, project_id)
