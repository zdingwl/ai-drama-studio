from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.db.session import get_db
from app.p17.common import resolve_episode_media
from app.p17.schemas import P17ReviewCommand, PostCandidateRead, ReplicaFinalOutputRead
from app.p17.service import (
    accept_post_candidate,
    create_post_task,
    get_final_output,
    list_post_candidates,
    reject_post_candidate,
    run_post_task,
)
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(tags=["p17-post-production"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post(
    "/projects/{project_id}/commands/post-production",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_post_production_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_post_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_post_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/post-production/candidates", response_model=list[PostCandidateRead])
def list_post_candidates_route(project_id: str, db: Session = Depends(get_db)) -> list[PostCandidateRead]:
    return list_post_candidates(db, project_id)


@router.post(
    "/projects/{project_id}/post-production/candidates/{candidate_id}/commands/accept",
    response_model=ReplicaFinalOutputRead,
)
def accept_post_candidate_route(
    project_id: str,
    candidate_id: str,
    command: P17ReviewCommand,
    db: Session = Depends(get_db),
) -> ReplicaFinalOutputRead:
    return accept_post_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post(
    "/projects/{project_id}/post-production/candidates/{candidate_id}/commands/reject",
    response_model=PostCandidateRead,
)
def reject_post_candidate_route(
    project_id: str,
    candidate_id: str,
    command: P17ReviewCommand,
    db: Session = Depends(get_db),
) -> PostCandidateRead:
    return reject_post_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.get("/projects/{project_id}/final-output", response_model=ReplicaFinalOutputRead)
def get_final_output_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaFinalOutputRead:
    return get_final_output(db, project_id)


@router.get("/projects/{project_id}/final-output/media/{task_id}/{episode_id}/{kind}")
def get_final_output_media_route(
    project_id: str,
    task_id: str,
    episode_id: str,
    kind: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise AppError("P17_TASK_NOT_FOUND", "Final Output Task 不存在", status_code=404)
    path = resolve_episode_media(project_id, task_id, episode_id, kind)
    media_type = "video/mp4" if kind == "video" else "application/x-subrip"
    return FileResponse(path, media_type=media_type)
