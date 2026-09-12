from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.p14.voice_catalog import TargetVoiceCatalogRead, get_target_voice_catalog

router = APIRouter(tags=["p14-target-audio-timing"])


@router.get("/projects/{project_id}/target-audio/voices", response_model=TargetVoiceCatalogRead)
def get_target_voice_catalog_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> TargetVoiceCatalogRead:
    return get_target_voice_catalog(db, project_id)
