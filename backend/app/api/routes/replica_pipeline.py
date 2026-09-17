from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.replica_pipeline.asset_images import (
    ASSET_PROMPT_TASK_TYPE,
    accept_asset_image_candidate,
    asset_image_media_path,
    create_asset_workspace_task,
    create_asset_images_task,
    extract_asset_workspace,
    get_asset_workspace,
    get_asset_images,
    list_asset_image_candidates,
    reject_asset_image_candidate,
    run_asset_images_task,
)
from app.replica_pipeline.h3_prompting import create_h3_prompt_task, get_h3_prompts, run_h3_prompt_task
from app.replica_pipeline.localized_storyboard import (
    accept_localized_storyboard_candidate,
    create_localized_storyboard_task,
    get_localized_storyboard,
    list_localized_storyboard_candidates,
    reject_localized_storyboard_candidate,
    run_localized_storyboard_task,
    update_localized_storyboard_shot,
)
from app.replica_pipeline.schemas import (
    AssetImageCandidateRead,
    AssetImagesRead,
    AssetWorkspaceRead,
    AssetWorkspaceSelectionCommand,
    H3PromptsRead,
    LocalizedStoryboardCandidateRead,
    LocalizedStoryboardRead,
    LocalizedStoryboardShotEditCommand,
    PipelineReviewCommand,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read


router = APIRouter(tags=["replica-five-step-pipeline"])


def _session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)


@router.post("/projects/{project_id}/commands/localized-storyboard", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def localized_storyboard_command(project_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], db: Session = Depends(get_db)) -> TaskRead:
    task = create_localized_storyboard_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status.value == "queued":
        background_tasks.add_task(run_localized_storyboard_task, _session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/localized-storyboard", response_model=LocalizedStoryboardRead)
def localized_storyboard_read(project_id: str, db: Session = Depends(get_db)) -> LocalizedStoryboardRead:
    return get_localized_storyboard(db, project_id)


@router.get("/projects/{project_id}/localized-storyboard/candidates", response_model=list[LocalizedStoryboardCandidateRead])
def localized_storyboard_candidates(project_id: str, db: Session = Depends(get_db)) -> list[LocalizedStoryboardCandidateRead]:
    return list_localized_storyboard_candidates(db, project_id)


@router.post("/projects/{project_id}/localized-storyboard/candidates/{candidate_id}/commands/accept", response_model=LocalizedStoryboardRead)
def localized_storyboard_accept(project_id: str, candidate_id: str, command: PipelineReviewCommand, db: Session = Depends(get_db)) -> LocalizedStoryboardRead:
    return accept_localized_storyboard_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post("/projects/{project_id}/localized-storyboard/candidates/{candidate_id}/commands/reject", response_model=LocalizedStoryboardCandidateRead)
def localized_storyboard_reject(project_id: str, candidate_id: str, command: PipelineReviewCommand, db: Session = Depends(get_db)) -> LocalizedStoryboardCandidateRead:
    return reject_localized_storyboard_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post("/projects/{project_id}/localized-storyboard/commands/update-shot", response_model=LocalizedStoryboardCandidateRead)
def localized_storyboard_update_shot(project_id: str, command: LocalizedStoryboardShotEditCommand, db: Session = Depends(get_db)) -> LocalizedStoryboardCandidateRead:
    return update_localized_storyboard_shot(db, project_id=project_id, command=command)


@router.post("/projects/{project_id}/commands/asset-images", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def asset_images_command(project_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], db: Session = Depends(get_db)) -> TaskRead:
    task = create_asset_images_task(db, project_id=project_id, idempotency_key=idempotency_key, regenerate=False)
    if task.status.value == "queued":
        background_tasks.add_task(run_asset_images_task, _session_factory(db), task.id)
    return task_to_read(task)


@router.post("/projects/{project_id}/commands/asset-images/regenerate", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def asset_images_regenerate_command(project_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], db: Session = Depends(get_db)) -> TaskRead:
    task = create_asset_images_task(db, project_id=project_id, idempotency_key=idempotency_key, regenerate=True)
    if task.status.value == "queued":
        background_tasks.add_task(run_asset_images_task, _session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/asset-workspace", response_model=AssetWorkspaceRead)
def asset_workspace_read(project_id: str, db: Session = Depends(get_db)) -> AssetWorkspaceRead:
    return get_asset_workspace(db, project_id)


@router.post("/projects/{project_id}/asset-workspace/commands/extract", response_model=AssetWorkspaceRead)
def asset_workspace_extract(project_id: str, db: Session = Depends(get_db)) -> AssetWorkspaceRead:
    return extract_asset_workspace(db, project_id)


@router.post("/projects/{project_id}/asset-workspace/commands/prompts", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def asset_workspace_prompts(project_id: str, command: AssetWorkspaceSelectionCommand, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], db: Session = Depends(get_db)) -> TaskRead:
    task = create_asset_workspace_task(db, project_id=project_id, idempotency_key=idempotency_key, operation="prompts", target_asset_ids=command.target_asset_ids)
    if task.status.value == "queued": background_tasks.add_task(run_asset_images_task, _session_factory(db), task.id)
    return task_to_read(task)


@router.post("/projects/{project_id}/asset-workspace/commands/images", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def asset_workspace_images(project_id: str, command: AssetWorkspaceSelectionCommand, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], db: Session = Depends(get_db)) -> TaskRead:
    task = create_asset_workspace_task(db, project_id=project_id, idempotency_key=idempotency_key, operation="images", target_asset_ids=command.target_asset_ids)
    if task.status.value == "queued": background_tasks.add_task(run_asset_images_task, _session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/asset-images", response_model=AssetImagesRead)
def asset_images_read(project_id: str, db: Session = Depends(get_db)) -> AssetImagesRead:
    return get_asset_images(db, project_id)


@router.get("/projects/{project_id}/asset-images/candidates", response_model=list[AssetImageCandidateRead])
def asset_images_candidates(project_id: str, db: Session = Depends(get_db)) -> list[AssetImageCandidateRead]:
    return list_asset_image_candidates(db, project_id)


@router.get("/projects/{project_id}/asset-images/media/{reference_id}")
def asset_images_media(project_id: str, reference_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return FileResponse(asset_image_media_path(db, project_id, reference_id), media_type="image/png")


@router.post("/projects/{project_id}/asset-images/candidates/{candidate_id}/commands/accept", response_model=AssetImagesRead)
def asset_images_accept(project_id: str, candidate_id: str, command: PipelineReviewCommand, db: Session = Depends(get_db)) -> AssetImagesRead:
    return accept_asset_image_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post("/projects/{project_id}/asset-images/candidates/{candidate_id}/commands/reject", response_model=AssetImageCandidateRead)
def asset_images_reject(project_id: str, candidate_id: str, command: PipelineReviewCommand, db: Session = Depends(get_db)) -> AssetImageCandidateRead:
    return reject_asset_image_candidate(db, project_id=project_id, candidate_id=candidate_id, command=command)


@router.post("/projects/{project_id}/commands/h3-prompts", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def h3_prompts_command(project_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], db: Session = Depends(get_db)) -> TaskRead:
    task = create_h3_prompt_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status.value == "queued":
        background_tasks.add_task(run_h3_prompt_task, _session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/h3-prompts", response_model=H3PromptsRead)
def h3_prompts_read(project_id: str, db: Session = Depends(get_db)) -> H3PromptsRead:
    return get_h3_prompts(db, project_id)
