from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.shot_breakdown.schemas import ShotBreakdownRead, ShotBreakdownRevisionSummary
from app.shot_breakdown.service_v2 import (
    create_shot_breakdown_task,
    get_shot_breakdown,
    list_shot_breakdown_revisions,
    run_p8_shot_breakdown_task,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["shot-breakdown"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@router.post(
    "/projects/{project_id}/commands/shot-breakdown",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_shot_breakdown_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_shot_breakdown_task(db, project_id=project_id, idempotency_key=idempotency_key)
    background_tasks.add_task(run_p8_shot_breakdown_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/shot-breakdown", response_model=ShotBreakdownRead)
def get_shot_breakdown_route(project_id: str, db: Session = Depends(get_db)) -> ShotBreakdownRead:
    return get_shot_breakdown(db, project_id)


@router.get(
    "/projects/{project_id}/shot-breakdown/revisions",
    response_model=list[ShotBreakdownRevisionSummary],
)
def list_shot_breakdown_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[ShotBreakdownRevisionSummary]:
    return list_shot_breakdown_revisions(db, project_id)
