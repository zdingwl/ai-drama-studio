from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.sources.schemas import EpisodeRead, EpisodeReorderRequest, SourceAssetRead, SourceDocumentRead
from app.sources.service import (
    get_current_document,
    ingest_text_upload,
    ingest_video_uploads,
    list_episodes,
    list_source_assets,
    reorder_episodes,
)

router = APIRouter(prefix="/projects/{project_id}/sources", tags=["sources"])


@router.get("/assets", response_model=list[SourceAssetRead])
def list_source_assets_route(project_id: str, db: Session = Depends(get_db)) -> list[SourceAssetRead]:
    return list_source_assets(db, project_id)


@router.post("/videos", response_model=list[EpisodeRead], status_code=status.HTTP_201_CREATED)
async def upload_videos_route(
    project_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> list[EpisodeRead]:
    return await ingest_video_uploads(db, project_id, files)


@router.get("/episodes", response_model=list[EpisodeRead])
def list_episodes_route(project_id: str, db: Session = Depends(get_db)) -> list[EpisodeRead]:
    return list_episodes(db, project_id)


@router.post("/episodes/reorder", response_model=list[EpisodeRead])
def reorder_episodes_route(
    project_id: str,
    payload: EpisodeReorderRequest,
    db: Session = Depends(get_db),
) -> list[EpisodeRead]:
    return reorder_episodes(db, project_id, payload.episode_ids)


@router.post("/document", response_model=SourceDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document_route(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SourceDocumentRead:
    return await ingest_text_upload(db, project_id, file)


@router.get("/document", response_model=SourceDocumentRead)
def get_document_route(project_id: str, db: Session = Depends(get_db)) -> SourceDocumentRead:
    return get_current_document(db, project_id)
