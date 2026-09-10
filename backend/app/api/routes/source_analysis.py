from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.source_analysis.schemas import SourceAnalysisStatusRead, SourceScriptRead
from app.source_analysis.service import (
    create_source_analysis_task,
    get_source_analysis_status,
    get_source_script,
    run_source_analysis_task,
)


router = APIRouter(tags=["source-analysis"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.get("/projects/{project_id}/source-analysis", response_model=SourceAnalysisStatusRead)
def get_source_analysis_route(project_id: str, db: Session = Depends(get_db)) -> SourceAnalysisStatusRead:
    return get_source_analysis_status(db, project_id)


@router.post(
    "/projects/{project_id}/commands/source-analysis",
    response_model=SourceAnalysisStatusRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_analysis_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> SourceAnalysisStatusRead:
    task = create_source_analysis_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task is not None and task.status.value == "queued":
        background_tasks.add_task(run_source_analysis_task, _request_session_factory(db), task.id)
    return get_source_analysis_status(db, project_id)


@router.get("/projects/{project_id}/source-script", response_model=SourceScriptRead)
def get_source_script_route(project_id: str, db: Session = Depends(get_db)) -> SourceScriptRead:
    return get_source_script(db, project_id)
