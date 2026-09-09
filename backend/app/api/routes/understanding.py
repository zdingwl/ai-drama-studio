from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.understanding.schemas import SourceBibleEditCommand, SourceBibleRead, SourceBibleRevisionSummary
from app.understanding.service import (
    create_source_bible_task,
    edit_source_bible,
    get_source_bible,
    list_source_bible_revisions,
    run_p7_source_bible_task,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(tags=["source-understanding"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@router.post(
    "/projects/{project_id}/commands/source-bible",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_bible_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_source_bible_task(db, project_id=project_id, idempotency_key=idempotency_key)
    background_tasks.add_task(run_p7_source_bible_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/source-bible", response_model=SourceBibleRead)
def get_source_bible_route(project_id: str, db: Session = Depends(get_db)) -> SourceBibleRead:
    return get_source_bible(db, project_id)


@router.get(
    "/projects/{project_id}/source-bible/revisions",
    response_model=list[SourceBibleRevisionSummary],
)
def list_source_bible_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[SourceBibleRevisionSummary]:
    return list_source_bible_revisions(db, project_id)


@router.post(
    "/projects/{project_id}/source-bible/commands/edit",
    response_model=SourceBibleRead,
    status_code=status.HTTP_201_CREATED,
)
def edit_source_bible_route(
    project_id: str,
    command: SourceBibleEditCommand,
    db: Session = Depends(get_db),
) -> SourceBibleRead:
    return edit_source_bible(db, project_id=project_id, command=command)
