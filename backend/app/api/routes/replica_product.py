from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.replica_product.schemas import ReplicaProductWorkflowRead
from app.replica_product.service import (
    create_adaptation_task,
    create_final_output_task,
    create_generation_pipeline_task,
    get_replica_product_workflow,
    run_adaptation_task,
    run_final_output_task,
    run_generation_pipeline_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["replica-product"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.get("/projects/{project_id}/replica-workflow", response_model=ReplicaProductWorkflowRead)
def get_replica_workflow_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaProductWorkflowRead:
    return get_replica_product_workflow(db, project_id)


@router.post(
    "/projects/{project_id}/commands/replica-adaptation",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_replica_adaptation_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_adaptation_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_adaptation_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/replica-generation",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_replica_generation_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_generation_pipeline_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_generation_pipeline_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/replica-final-output",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_replica_final_output_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_final_output_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_final_output_task, _request_session_factory(db), task.id)
    return task_to_read(task)
