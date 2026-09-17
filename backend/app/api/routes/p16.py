from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.p16.common import attempt_media_path
from app.p16.models import ReplicaGenerationAttempt
from app.p16.schemas import (
    GenerationAttemptRead,
    H3RuntimeReadinessRead,
    P16ReviewCommand,
    P16SelectionCandidateRead,
    ReplicaGeneratedVideoRead,
    ReplicaGenerationSelectionRead,
)
from app.p16.service import (
    accept_selection_candidate,
    create_generation_task,
    create_segment_regeneration_task,
    get_generated_video,
    get_generation_selection,
    get_runtime_readiness,
    list_generation_attempts,
    list_selection_candidates,
    reject_selection_candidate,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["p16-video-generation"])


@router.get(
    "/projects/{project_id}/video-generation/runtime-readiness",
    response_model=H3RuntimeReadinessRead,
)
def get_video_generation_runtime_readiness_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> H3RuntimeReadinessRead:
    return get_runtime_readiness(db, project_id)


@router.post(
    "/projects/{project_id}/commands/video-generation",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_video_generation_route(
    project_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_generation_task(db, project_id=project_id, idempotency_key=idempotency_key)
    return task_to_read(task)


@router.post(
    "/projects/{project_id}/video-generation/segments/{generation_segment_id}/commands/regenerate",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_video_segment_route(
    project_id: str,
    generation_segment_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_segment_regeneration_task(
        db,
        project_id=project_id,
        generation_segment_id=generation_segment_id,
        idempotency_key=idempotency_key,
    )
    return task_to_read(task)


@router.get("/projects/{project_id}/video-generation/attempts", response_model=list[GenerationAttemptRead])
def list_video_generation_attempts_route(project_id: str, db: Session = Depends(get_db)) -> list[GenerationAttemptRead]:
    return list_generation_attempts(db, project_id)


# Legacy candidate review endpoints remain readable/callable for historical P16 data and debug
# clients. The Replica five-step ordinary UI no longer requires an extra accept/reject action.
@router.get("/projects/{project_id}/video-generation/candidates", response_model=list[P16SelectionCandidateRead])
def list_video_generation_candidates_route(project_id: str, db: Session = Depends(get_db)) -> list[P16SelectionCandidateRead]:
    return list_selection_candidates(db, project_id)


@router.get("/projects/{project_id}/video-generation/media/{attempt_id}")
def get_video_generation_media_route(project_id: str, attempt_id: str, db: Session = Depends(get_db)) -> FileResponse:
    attempt = db.get(ReplicaGenerationAttempt, attempt_id)
    if attempt is None or attempt.project_id != project_id:
        raise AppError("P16_ATTEMPT_NOT_FOUND", "GenerationAttempt 不存在", status_code=404)
    return FileResponse(attempt_media_path(attempt), media_type=attempt.mime_type)


@router.post(
    "/projects/{project_id}/video-generation/candidates/{candidate_id}/commands/accept",
    response_model=ReplicaGenerationSelectionRead,
)
def accept_video_generation_candidate_route(
    project_id: str,
    candidate_id: str,
    command: P16ReviewCommand,
    db: Session = Depends(get_db),
) -> ReplicaGenerationSelectionRead:
    return accept_selection_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post(
    "/projects/{project_id}/video-generation/candidates/{candidate_id}/commands/reject",
    response_model=P16SelectionCandidateRead,
)
def reject_video_generation_candidate_route(
    project_id: str,
    candidate_id: str,
    command: P16ReviewCommand,
    db: Session = Depends(get_db),
) -> P16SelectionCandidateRead:
    return reject_selection_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.get("/projects/{project_id}/generated-video", response_model=ReplicaGeneratedVideoRead)
def get_generated_video_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaGeneratedVideoRead:
    return get_generated_video(db, project_id)


@router.get("/projects/{project_id}/generation-selection", response_model=ReplicaGenerationSelectionRead)
def get_generation_selection_route(project_id: str, db: Session = Depends(get_db)) -> ReplicaGenerationSelectionRead:
    return get_generation_selection(db, project_id)
