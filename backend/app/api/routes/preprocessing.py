from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.preprocessing.schemas import EpisodeShotBoundaryRead
from app.preprocessing.service import (
    create_shot_boundary_task,
    get_episode_shot_boundary,
    get_shot_media_path,
    run_p5_shot_boundary_task,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["preprocessing"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@router.post(
    "/projects/{project_id}/episodes/{episode_id}/commands/shot-boundary",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_shot_boundary_route(
    project_id: str,
    episode_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_shot_boundary_task(
        db,
        project_id=project_id,
        episode_id=episode_id,
        idempotency_key=idempotency_key,
    )
    background_tasks.add_task(
        run_p5_shot_boundary_task,
        _request_session_factory(db),
        task.id,
    )
    return task_to_read(task)


@router.get(
    "/projects/{project_id}/episodes/{episode_id}/shot-boundary",
    response_model=EpisodeShotBoundaryRead,
)
def get_shot_boundary_route(
    project_id: str,
    episode_id: str,
    db: Session = Depends(get_db),
) -> EpisodeShotBoundaryRead:
    return get_episode_shot_boundary(db, project_id, episode_id)


@router.get("/projects/{project_id}/episodes/{episode_id}/shot-boundary/shots/{shot_id}/thumbnail")
def get_shot_thumbnail_route(
    project_id: str,
    episode_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    path = get_shot_media_path(
        db,
        project_id=project_id,
        episode_id=episode_id,
        shot_id=shot_id,
        kind="thumbnail",
    )
    return FileResponse(path, media_type="image/jpeg")


@router.get("/projects/{project_id}/episodes/{episode_id}/shot-boundary/shots/{shot_id}/reference-clip")
def get_shot_reference_clip_route(
    project_id: str,
    episode_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    path = get_shot_media_path(
        db,
        project_id=project_id,
        episode_id=episode_id,
        shot_id=shot_id,
        kind="reference_clip",
    )
    return FileResponse(path, media_type="video/mp4")
