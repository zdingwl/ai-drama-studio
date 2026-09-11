from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.target_assets.schemas import (
    ReplicaTargetAssetsRead,
    ReplicaTargetAssetsRevisionSummary,
    TargetAssetsGenerateCommand,
)
from app.target_assets.service import (
    approve_target_assets_candidate,
    create_target_assets_task,
    find_reference_asset,
    get_target_assets,
    list_target_assets_revisions,
    run_target_assets_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["target-assets"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post(
    "/projects/{project_id}/commands/target-assets",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_target_assets_route(
    project_id: str,
    command: TargetAssetsGenerateCommand,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_target_assets_task(
        db,
        project_id=project_id,
        command=command,
        idempotency_key=idempotency_key,
    )
    # P13 generation is stochastic and the worker needs the exact requested regeneration scope.
    # Persist it before scheduling the background worker. It is execution metadata only; the formal
    # Task Artifact hard input remains exactly CURRENT TARGET_BIBLE.
    if task.status == TaskStatus.QUEUED:
        checkpoint = dict(task.checkpoint_json or {})
        if "requested_target_asset_ids" not in checkpoint:
            checkpoint.update(
                {
                    "stage": "queued",
                    "requested_target_asset_ids": list(command.target_asset_ids),
                }
            )
            task.checkpoint_json = checkpoint
            db.add(task)
            db.commit()
            db.refresh(task)
        background_tasks.add_task(
            run_target_assets_task,
            _request_session_factory(db),
            task.id,
        )
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/target-assets/{candidate_id}/approve",
    response_model=ReplicaTargetAssetsRead,
)
def approve_target_assets_route(
    project_id: str,
    candidate_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> ReplicaTargetAssetsRead:
    return approve_target_assets_candidate(
        db,
        project_id=project_id,
        candidate_id=candidate_id,
        idempotency_key=idempotency_key,
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


@router.get("/projects/{project_id}/target-assets/references/{reference_asset_id}")
def get_target_asset_reference_route(
    project_id: str,
    reference_asset_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    reference = find_reference_asset(
        db,
        project_id=project_id,
        reference_asset_id=reference_asset_id,
    )
    return FileResponse(reference.path, media_type=reference.media_type, filename=reference.path.name)
