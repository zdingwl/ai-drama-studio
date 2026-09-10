from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.source_resolution.adjudication_v2 import adjudicate_source_resolution
from app.source_resolution.schemas import (
    ManualResolutionCommand,
    SourceResolutionKind,
    SourceResolutionRead,
    SourceResolutionRevisionSummary,
)
from app.source_resolution.service_v2 import (
    create_source_resolution_task,
    get_source_resolution,
    list_source_resolution_revisions,
    run_p9_source_resolution_task,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["source-resolution"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post(
    "/projects/{project_id}/commands/source-resolution",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_resolution_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_source_resolution_task(db, project_id=project_id, idempotency_key=idempotency_key)
    background_tasks.add_task(run_p9_source_resolution_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/source-resolution", response_model=SourceResolutionRead)
def get_source_resolution_route(project_id: str, db: Session = Depends(get_db)) -> SourceResolutionRead:
    return get_source_resolution(db, project_id)


@router.get(
    "/projects/{project_id}/source-resolution/revisions",
    response_model=list[SourceResolutionRevisionSummary],
)
def list_source_resolution_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[SourceResolutionRevisionSummary]:
    return list_source_resolution_revisions(db, project_id)


@router.post(
    "/projects/{project_id}/source-resolution/{kind}/commands/adjudicate",
    response_model=SourceResolutionRead,
)
def adjudicate_source_resolution_route(
    project_id: str,
    kind: SourceResolutionKind,
    payload: ManualResolutionCommand,
    db: Session = Depends(get_db),
) -> SourceResolutionRead:
    adjudicate_source_resolution(db, project_id=project_id, kind=kind, command=payload)
    return get_source_resolution(db, project_id)
