from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.service import invalidate_current_artifact_type
from app.db.session import get_db
from app.projects.enums import SourceUnderstandingProvider
from app.projects.models import Project
from app.skills.models import ArtifactType
from app.understanding.evidence_reference_runtime import run_p7_source_bible_task
from app.understanding.runtime_config import P7RuntimeConfig, get_p7_runtime_config, update_p7_runtime_config
from app.understanding.schemas import SourceBibleEditCommand, SourceBibleRead, SourceBibleRevisionSummary
from app.understanding.service import (
    create_source_bible_task,
    edit_source_bible,
    get_source_bible,
    list_source_bible_revisions,
)
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(tags=["source-understanding"])


def _request_session_factory(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def _runtime_profile_changed(before: P7RuntimeConfig, after: P7RuntimeConfig) -> set[SourceUnderstandingProvider]:
    changed: set[SourceUnderstandingProvider] = set()
    if (
        before.doubao.model != after.doubao.model
        or before.doubao.base_url != after.doubao.base_url
        or before.doubao.video_fps != after.doubao.video_fps
    ):
        changed.add(SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API)
    if before.qwen38.model != after.qwen38.model or before.qwen38.base_url != after.qwen38.base_url:
        changed.add(SourceUnderstandingProvider.QWEN3_8_27B_LOCAL)
    if (
        before.qwen3_vl_8b.model != after.qwen3_vl_8b.model
        or before.qwen3_vl_8b.base_url != after.qwen3_vl_8b.base_url
    ):
        changed.update(
            {
                SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL,
                SourceUnderstandingProvider.QWEN3_VL_LOCAL,
            }
        )
    return changed


@router.get("/source-understanding/runtime-config", response_model=P7RuntimeConfig)
def get_source_understanding_runtime_config_route() -> P7RuntimeConfig:
    return get_p7_runtime_config()


@router.put("/source-understanding/runtime-config", response_model=P7RuntimeConfig)
def update_source_understanding_runtime_config_route(
    payload: P7RuntimeConfig,
    db: Session = Depends(get_db),
) -> P7RuntimeConfig:
    before = get_p7_runtime_config()
    after = update_p7_runtime_config(payload)
    changed = _runtime_profile_changed(before, after)
    if changed:
        project_ids = list(
            db.scalars(
                select(Project.id).where(Project.source_understanding_provider.in_(tuple(changed)))
            ).all()
        )
        for project_id in project_ids:
            invalidate_current_artifact_type(
                db,
                project_id=project_id,
                artifact_type=ArtifactType.SOURCE_BIBLE,
            )
    return after


@router.post(
    "/projects/{project_id}/commands/source-bible",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_bible_route(
    project_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    task = create_source_bible_task(db, project_id=project_id, idempotency_key=idempotency_key)
    background_tasks.add_task(run_p7_source_bible_task, _request_session_factory(db), task.id)
    return task_to_read(task)


@router.get("/projects/{project_id}/source-bible", response_model=SourceBibleRead)
def get_source_bible_route(project_id: str, db: Session = Depends(get_db)) -> SourceBibleRead:
    return get_source_bible(db, project_id)


@router.get(
    "/projects/{project_id}/source-bible/revisions",
    response_model=list[SourceBibleRevisionSummary],
)
def list_source_bible_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[SourceBibleRevisionSummary]:
    return list_source_bible_revisions(db, project_id)


@router.post(
    "/projects/{project_id}/source-bible/commands/edit",
    response_model=SourceBibleRead,
    status_code=status.HTTP_201_CREATED,
)
def edit_source_bible_route(
    project_id: str,
    command: SourceBibleEditCommand,
    db: Session = Depends(get_db),
) -> SourceBibleRead:
    return edit_source_bible(db, project_id=project_id, command=command)
