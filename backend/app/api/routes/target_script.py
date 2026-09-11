from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.target_script.schemas import ReplicaTargetScriptRead, ReplicaTargetScriptRevisionSummary
from app.target_script.service import (
    create_target_script_task,
    get_target_script,
    list_target_script_revisions,
    run_target_script_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["target-script"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post(
    "/projects/{project_id}/commands/target-script",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_target_script_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_target_script_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(
            run_target_script_task,
            _request_session_factory(db),
            task.id,
        )
    return task_to_read(task)


@router.get("/projects/{project_id}/target-script", response_model=ReplicaTargetScriptRead)
def get_target_script_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaTargetScriptRead:
    return get_target_script(db, project_id)


@router.get(
    "/projects/{project_id}/target-script/revisions",
    response_model=list[ReplicaTargetScriptRevisionSummary],
)
def list_target_script_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[ReplicaTargetScriptRevisionSummary]:
    return list_target_script_revisions(db, project_id)
