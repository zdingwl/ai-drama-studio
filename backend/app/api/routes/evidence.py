from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.evidence.schemas import EpisodeSourceEvidenceRead
from app.evidence.service_v4 import (
    create_source_evidence_task,
    get_episode_source_evidence,
    run_p6_source_evidence_task,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["source-evidence"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@router.post(
    "/projects/{project_id}/episodes/{episode_id}/commands/source-evidence",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_evidence_route(
    project_id: str,
    episode_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_source_evidence_task(
        db,
        project_id=project_id,
        episode_id=episode_id,
        idempotency_key=idempotency_key,
    )
    background_tasks.add_task(
        run_p6_source_evidence_task,
        _request_session_factory(db),
        task.id,
    )
    return task_to_read(task)


@router.get(
    "/projects/{project_id}/episodes/{episode_id}/source-evidence",
    response_model=EpisodeSourceEvidenceRead,
)
def get_source_evidence_route(
    project_id: str,
    episode_id: str,
    db: Session = Depends(get_db),
) -> EpisodeSourceEvidenceRead:
    return get_episode_source_evidence(db, project_id, episode_id)
