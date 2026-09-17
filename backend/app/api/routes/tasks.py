from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.p16.runtime import P16_SEGMENT_TASK_TYPE, P16_TASK_TYPE, replace_generation_task_for_retry_if_needed
from app.workflow.p4_acceptance import P4AcceptanceScenario, build_p4_acceptance_payload
from app.workflow.schemas import TaskCommandCreate, TaskRead
from app.workflow.task_service import (
    cancel_task,
    create_task_from_command,
    get_task,
    list_tasks,
    resume_task,
    retry_task,
    task_to_read,
)


router = APIRouter(tags=["tasks"])


@router.post(
    "/projects/{project_id}/commands/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_task_command_route(
    project_id: str,
    payload: TaskCommandCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_task_from_command(
        db,
        project_id=project_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/p4-acceptance/{scenario}",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_p4_acceptance_task_route(
    project_id: str,
    scenario: P4AcceptanceScenario,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    payload = build_p4_acceptance_payload(
        project_id=project_id,
        scenario=scenario,
        idempotency_key=idempotency_key,
    )
    task = create_task_from_command(
        db,
        project_id=project_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    # Execution is owned by the persistent queue dispatcher started in app.main lifespan.
    return task_to_read(task)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
def list_tasks_route(project_id: str, db: Session = Depends(get_db)) -> list[TaskRead]:
    return [task_to_read(task) for task in list_tasks(db, project_id)]


@router.get("/projects/{project_id}/tasks/{task_id}", response_model=TaskRead)
def get_task_route(project_id: str, task_id: str, db: Session = Depends(get_db)) -> TaskRead:
    return task_to_read(get_task(db, project_id, task_id))


@router.post("/projects/{project_id}/tasks/{task_id}/commands/cancel", response_model=TaskRead)
def cancel_task_route(project_id: str, task_id: str, db: Session = Depends(get_db)) -> TaskRead:
    return task_to_read(cancel_task(db, project_id, task_id))


@router.post("/projects/{project_id}/tasks/{task_id}/commands/retry", response_model=TaskRead)
def retry_task_route(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_db),
) -> TaskRead:
    existing = get_task(db, project_id, task_id)
    if existing.task_type in {P16_TASK_TYPE, P16_SEGMENT_TASK_TYPE}:
        replacement = replace_generation_task_for_retry_if_needed(db, project_id=project_id, task=existing)
        if replacement is not None:
            return task_to_read(replacement)
    task = retry_task(db, project_id, task_id)
    return task_to_read(task)


@router.post("/projects/{project_id}/tasks/{task_id}/commands/resume", response_model=TaskRead)
def resume_task_route(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_db),
) -> TaskRead:
    existing = get_task(db, project_id, task_id)
    if existing.task_type in {P16_TASK_TYPE, P16_SEGMENT_TASK_TYPE}:
        replacement = replace_generation_task_for_retry_if_needed(db, project_id=project_id, task=existing)
        if replacement is not None:
            return task_to_read(replacement)
    task = resume_task(db, project_id, task_id)
    return task_to_read(task)
