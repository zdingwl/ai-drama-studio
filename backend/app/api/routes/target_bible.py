from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.target_bible.schemas import ReplicaTargetBibleRead, ReplicaTargetBibleRevisionSummary
from app.target_bible.service import (
    create_replica_target_bible_task,
    get_replica_target_bible,
    list_replica_target_bible_revisions,
    run_replica_target_bible_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["target-bible"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post(
    "/projects/{project_id}/commands/target-bible",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_target_bible_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_replica_target_bible_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(
            run_replica_target_bible_task,
            _request_session_factory(db),
            task.id,
        )
    return task_to_read(task)


@router.get("/projects/{project_id}/target-bible", response_model=ReplicaTargetBibleRead)
def get_target_bible_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaTargetBibleRead:
    return get_replica_target_bible(db, project_id)


@router.get(
    "/projects/{project_id}/target-bible/revisions",
    response_model=list[ReplicaTargetBibleRevisionSummary],
)
def list_target_bible_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[ReplicaTargetBibleRevisionSummary]:
    return list_replica_target_bible_revisions(db, project_id)
