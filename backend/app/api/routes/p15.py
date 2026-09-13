from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.p15.schemas import (
    P15CandidateRead,
    P15ReviewCommand,
    ReplicaGenerationSegmentsRead,
    ReplicaTargetStoryboardRead,
)
from app.p15.service import (
    accept_storyboard_candidate,
    create_storyboard_task,
    get_generation_segments,
    get_storyboard,
    list_storyboard_candidates,
    reject_storyboard_candidate,
    run_storyboard_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(tags=["p15-storyboard"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post(
    "/projects/{project_id}/commands/replica-storyboard",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_replica_storyboard_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_storyboard_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_storyboard_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/target-storyboard", response_model=ReplicaTargetStoryboardRead)
def get_target_storyboard_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaTargetStoryboardRead:
    return get_storyboard(db, project_id)


@router.get("/projects/{project_id}/generation-segments", response_model=ReplicaGenerationSegmentsRead)
def get_generation_segments_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaGenerationSegmentsRead:
    return get_generation_segments(db, project_id)


@router.get("/projects/{project_id}/target-storyboard/candidates", response_model=list[P15CandidateRead])
def list_target_storyboard_candidates_route(project_id: str, db: Session = Depends(get_db)) -> list[P15CandidateRead]:
    return list_storyboard_candidates(db, project_id)


@router.post(
    "/projects/{project_id}/target-storyboard/candidates/{candidate_id}/commands/accept",
    response_model=ReplicaTargetStoryboardRead,
)
def accept_target_storyboard_candidate_route(
    project_id: str,
    candidate_id: str,
    command: P15ReviewCommand,
    db: Session = Depends(get_db),
) -> ReplicaTargetStoryboardRead:
    return accept_storyboard_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post(
    "/projects/{project_id}/target-storyboard/candidates/{candidate_id}/commands/reject",
    response_model=P15CandidateRead,
)
def reject_target_storyboard_candidate_route(
    project_id: str,
    candidate_id: str,
    command: P15ReviewCommand,
    db: Session = Depends(get_db),
) -> P15CandidateRead:
    return reject_storyboard_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)
