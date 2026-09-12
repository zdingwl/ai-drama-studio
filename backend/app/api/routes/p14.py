from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.p14.schemas import (
    ReplicaTargetAudioRead,
    ReplicaTimingPlanRead,
    TargetAudioCandidateRead,
    TargetAudioGenerateCommand,
    TargetAudioReviewCommand,
    TimingPlanCandidateRead,
    TimingPlanReviewCommand,
)
from app.p14.service import (
    accept_target_audio_candidate,
    accept_timing_plan_candidate,
    create_target_audio_task,
    create_timing_plan_task,
    get_target_audio,
    get_timing_plan,
    list_target_audio_candidates,
    list_timing_plan_candidates,
    reject_target_audio_candidate,
    reject_timing_plan_candidate,
    resolve_target_audio_media_path,
    run_target_audio_task,
    run_timing_plan_task,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["p14-target-audio-timing"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


def _start_audio(
    *,
    project_id: str,
    command: TargetAudioGenerateCommand,
    background_tasks: BackgroundTasks,
    idempotency_key: str,
    db: Session,
    regenerate: bool,
) -> TaskRead:
    task = create_target_audio_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        command=command,
        regenerate=regenerate,
    )
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_target_audio_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/target-audio",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_target_audio_route(
    project_id: str,
    command: TargetAudioGenerateCommand,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return _start_audio(
        project_id=project_id,
        command=command,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        regenerate=False,
    )


@router.post(
    "/projects/{project_id}/commands/target-audio/regenerate",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_target_audio_route(
    project_id: str,
    command: TargetAudioGenerateCommand,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return _start_audio(
        project_id=project_id,
        command=command,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        regenerate=True,
    )


@router.get("/projects/{project_id}/target-audio", response_model=ReplicaTargetAudioRead)
def get_target_audio_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaTargetAudioRead:
    return get_target_audio(db, project_id)


@router.get("/projects/{project_id}/target-audio/candidates", response_model=list[TargetAudioCandidateRead])
def list_target_audio_candidates_route(
    project_id: str, db: Session = Depends(get_db)
) -> list[TargetAudioCandidateRead]:
    return list_target_audio_candidates(db, project_id)


@router.post(
    "/projects/{project_id}/target-audio/candidates/{candidate_id}/commands/accept",
    response_model=ReplicaTargetAudioRead,
)
def accept_target_audio_candidate_route(
    project_id: str,
    candidate_id: str,
    command: TargetAudioReviewCommand,
    db: Session = Depends(get_db),
) -> ReplicaTargetAudioRead:
    return accept_target_audio_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post(
    "/projects/{project_id}/target-audio/candidates/{candidate_id}/commands/reject",
    response_model=TargetAudioCandidateRead,
)
def reject_target_audio_candidate_route(
    project_id: str,
    candidate_id: str,
    command: TargetAudioReviewCommand,
    db: Session = Depends(get_db),
) -> TargetAudioCandidateRead:
    return reject_target_audio_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.get("/projects/{project_id}/target-audio/media/{task_id}/{clip_id}")
def get_target_audio_media_route(project_id: str, task_id: str, clip_id: str) -> FileResponse:
    path = resolve_target_audio_media_path(project_id, task_id, clip_id)
    return FileResponse(path)


def _start_timing(
    *,
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: str,
    db: Session,
    regenerate: bool,
) -> TaskRead:
    task = create_timing_plan_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        regenerate=regenerate,
    )
    if task.status == TaskStatus.QUEUED:
        background_tasks.add_task(run_timing_plan_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/commands/timing-plan",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_timing_plan_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return _start_timing(
        project_id=project_id,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        regenerate=False,
    )


@router.post(
    "/projects/{project_id}/commands/timing-plan/regenerate",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_timing_plan_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return _start_timing(
        project_id=project_id,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        regenerate=True,
    )


@router.get("/projects/{project_id}/timing-plan", response_model=ReplicaTimingPlanRead)
def get_timing_plan_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaTimingPlanRead:
    return get_timing_plan(db, project_id)


@router.get("/projects/{project_id}/timing-plan/candidates", response_model=list[TimingPlanCandidateRead])
def list_timing_plan_candidates_route(
    project_id: str, db: Session = Depends(get_db)
) -> list[TimingPlanCandidateRead]:
    return list_timing_plan_candidates(db, project_id)


@router.post(
    "/projects/{project_id}/timing-plan/candidates/{candidate_id}/commands/accept",
    response_model=ReplicaTimingPlanRead,
)
def accept_timing_plan_candidate_route(
    project_id: str,
    candidate_id: str,
    command: TimingPlanReviewCommand,
    db: Session = Depends(get_db),
) -> ReplicaTimingPlanRead:
    return accept_timing_plan_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post(
    "/projects/{project_id}/timing-plan/candidates/{candidate_id}/commands/reject",
    response_model=TimingPlanCandidateRead,
)
def reject_timing_plan_candidate_route(
    project_id: str,
    candidate_id: str,
    command: TimingPlanReviewCommand,
    db: Session = Depends(get_db),
) -> TimingPlanCandidateRead:
    return reject_timing_plan_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)
