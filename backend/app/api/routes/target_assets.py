from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.target_assets.schemas import (
    ReplicaTargetAssetsRead,
    ReplicaTargetAssetsRevisionSummary,
    TargetAssetsCandidateRead,
    TargetAssetsReviewCommand,
)
from app.target_assets.service import (
    accept_target_assets_candidate,
    create_target_assets_task,
    get_target_assets,
    list_target_assets_candidates,
    list_target_assets_revisions,
    reject_target_assets_candidate,
    run_target_assets_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["target-assets"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


def _start(
    *,
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: str,
    db: Session,
    regenerate: bool,
) -> TaskRead:
    task = create_target_assets_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        regenerate=regenerate,
    )
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(
            run_target_assets_task,
            _request_session_factory(db),
            task.id,
        )
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/target-assets",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_target_assets_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return _start(
        project_id=project_id,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        regenerate=False,
    )


@router.post(
    "/projects/{project_id}/commands/target-assets/regenerate",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_target_assets_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return _start(
        project_id=project_id,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        regenerate=True,
    )


@router.get("/projects/{project_id}/target-assets", response_model=ReplicaTargetAssetsRead)
def get_target_assets_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaTargetAssetsRead:
    return get_target_assets(db, project_id)


@router.get(
    "/projects/{project_id}/target-assets/revisions",
    response_model=list[ReplicaTargetAssetsRevisionSummary],
)
def list_target_assets_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[ReplicaTargetAssetsRevisionSummary]:
    return list_target_assets_revisions(db, project_id)


@router.get(
    "/projects/{project_id}/target-assets/candidates",
    response_model=list[TargetAssetsCandidateRead],
)
def list_target_assets_candidates_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[TargetAssetsCandidateRead]:
    return list_target_assets_candidates(db, project_id)


@router.post(
    "/projects/{project_id}/target-assets/candidates/{candidate_id}/commands/accept",
    response_model=ReplicaTargetAssetsRead,
)
def accept_target_assets_candidate_route(
    project_id: str,
    candidate_id: str,
    command: TargetAssetsReviewCommand,
    db: Session = Depends(get_db),
) -> ReplicaTargetAssetsRead:
    return accept_target_assets_candidate(
        db,
        project_id=project_id,
        candidate_id=candidate_id,
        command=command,
    )


@router.post(
    "/projects/{project_id}/target-assets/candidates/{candidate_id}/commands/reject",
    response_model=TargetAssetsCandidateRead,
)
def reject_target_assets_candidate_route(
    project_id: str,
    candidate_id: str,
    command: TargetAssetsReviewCommand,
    db: Session = Depends(get_db),
) -> TargetAssetsCandidateRead:
    return reject_target_assets_candidate(
        db,
        project_id=project_id,
        candidate_id=candidate_id,
        command=command,
    )
