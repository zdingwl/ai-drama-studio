from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.source_snapshot.schemas import (
    SourceVideoSnapshotRead,
    SourceVideoSnapshotRevisionSummary,
)
from app.source_snapshot.service import (
    finalize_source_video_snapshot,
    get_source_video_snapshot,
    list_source_video_snapshot_revisions,
)


router = APIRouter(tags=["source-video-snapshot"])


@router.post(
    "/projects/{project_id}/commands/source-video-snapshot",
    response_model=SourceVideoSnapshotRead,
)
def finalize_source_video_snapshot_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> SourceVideoSnapshotRead:
    return finalize_source_video_snapshot(db, project_id)


@router.get(
    "/projects/{project_id}/source-video-snapshot",
    response_model=SourceVideoSnapshotRead,
)
def get_source_video_snapshot_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> SourceVideoSnapshotRead:
    return get_source_video_snapshot(db, project_id)


@router.get(
    "/projects/{project_id}/source-video-snapshot/revisions",
    response_model=list[SourceVideoSnapshotRevisionSummary],
)
def list_source_video_snapshot_revisions_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[SourceVideoSnapshotRevisionSummary]:
    return list_source_video_snapshot_revisions(db, project_id)
