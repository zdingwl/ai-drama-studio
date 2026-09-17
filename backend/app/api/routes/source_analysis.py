from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.projects.enums import SOURCE_BIBLE_PROJECT_TYPES
from app.projects.service import get_project
from app.source_analysis.draft_service import edit_storyboard_draft, get_storyboard_draft
from app.source_analysis.schemas import (
    SourceAnalysisStatusRead,
    SourceScriptRead,
    StoryboardDraftRead,
    StoryboardShotEditCommand,
)
from app.source_analysis.script_service import get_source_script
from app.source_analysis.service import create_source_analysis_task, get_source_analysis_status


router = APIRouter(tags=["source-analysis"])


def _assert_supported_project(db: Session, project_id: str) -> None:
    project = get_project(db, project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError(
            "SOURCE_ANALYSIS_NOT_ALLOWED",
            "当前一键原片剧本 / 分镜工作区仅用于复刻短剧和重绘短剧",
            status_code=422,
        )


def _require_episode_id(episode_id: str | None) -> str:
    """Enforce the episode-first contract at the HTTP boundary."""
    if not episode_id or not episode_id.strip():
        raise AppError(
            "EPISODE_REQUIRED",
            "原片分析必须指定单个 Episode，禁止执行全集分析",
            status_code=422,
        )
    return episode_id


@router.get("/projects/{project_id}/source-analysis", response_model=SourceAnalysisStatusRead)
def get_source_analysis_route(
    project_id: str,
    episode_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SourceAnalysisStatusRead:
    _assert_supported_project(db, project_id)
    scoped_episode_id = _require_episode_id(episode_id)
    return get_source_analysis_status(db, project_id, episode_id=scoped_episode_id)


@router.post(
    "/projects/{project_id}/commands/source-analysis",
    response_model=SourceAnalysisStatusRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_analysis_route(
    project_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    episode_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SourceAnalysisStatusRead:
    _assert_supported_project(db, project_id)
    scoped_episode_id = _require_episode_id(episode_id)
    create_source_analysis_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        episode_id=scoped_episode_id,
    )
    # The persistent queue dispatcher owns execution; the HTTP request only persists the command.
    return get_source_analysis_status(db, project_id, episode_id=scoped_episode_id)


@router.get("/projects/{project_id}/source-script", response_model=SourceScriptRead)
def get_source_script_route(project_id: str, db: Session = Depends(get_db)) -> SourceScriptRead:
    _assert_supported_project(db, project_id)
    return get_source_script(db, project_id)


@router.get("/projects/{project_id}/storyboard-draft", response_model=StoryboardDraftRead)
def get_storyboard_draft_route(project_id: str, db: Session = Depends(get_db)) -> StoryboardDraftRead:
    _assert_supported_project(db, project_id)
    return get_storyboard_draft(db, project_id)


@router.post(
    "/projects/{project_id}/storyboard-draft/commands/edit-shot",
    response_model=StoryboardDraftRead,
    status_code=status.HTTP_201_CREATED,
)
def edit_storyboard_draft_route(
    project_id: str,
    payload: StoryboardShotEditCommand,
    db: Session = Depends(get_db),
) -> StoryboardDraftRead:
    _assert_supported_project(db, project_id)
    return edit_storyboard_draft(db, project_id=project_id, command=payload)
