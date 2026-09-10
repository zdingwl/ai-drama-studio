from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.evidence.service_v4 import is_p6_source_evidence_task, run_p6_source_evidence_task
from app.preprocessing.service import is_p5_shot_boundary_task, run_p5_shot_boundary_task
from app.shot_breakdown.service_v2 import P8_TASK_TYPE, run_p8_shot_breakdown_task
from app.understanding.evidence_reference_runtime import run_p7_source_bible_task
from app.understanding.service import P7_TASK_TYPE
from app.workflow.p4_acceptance import (
    P4AcceptanceScenario,
    build_p4_acceptance_payload,
    is_p4_acceptance_task,
    run_p4_acceptance_task,
)
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


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def _schedule_task_if_needed(
    background_tasks: BackgroundTasks,
    db: Session,
    task,
) -> None:
    session_factory = _request_session_factory(db)
    if is_p4_acceptance_task(task):
        background_tasks.add_task(run_p4_acceptance_task, session_factory, task.id)
    elif is_p5_shot_boundary_task(task):
        background_tasks.add_task(run_p5_shot_boundary_task, session_factory, task.id)
    elif is_p6_source_evidence_task(task):
        background_tasks.add_task(run_p6_source_evidence_task, session_factory, task.id)
    elif task.task_type == P7_TASK_TYPE:
        background_tasks.add_task(run_p7_source_bible_task, session_factory, task.id)
    elif task.task_type == P8_TASK_TYPE:
        background_tasks.add_task(run_p8_shot_breakdown_task, session_factory, task.id)


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
    background_tasks: BackgroundTasks,
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
    _schedule_task_if_needed(background_tasks, db, task)
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> TaskRead:
    task = retry_task(db, project_id, task_id)
    _schedule_task_if_needed(background_tasks, db, task)
    return task_to_read(task)


@router.post("/projects/{project_id}/tasks/{task_id}/commands/resume", response_model=TaskRead)
def resume_task_route(
    project_id: str,
    task_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> TaskRead:
    task = resume_task(db, project_id, task_id)
    _schedule_task_if_needed(background_tasks, db, task)
    return task_to_read(task)
