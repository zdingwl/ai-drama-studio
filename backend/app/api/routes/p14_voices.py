from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.p14.common import _assert_replica
from app.p14.provider import IndexTTS25Provider
from app.projects.service import get_project


class TTSVoiceOptionRead(BaseModel):
    voice_key: str
    display_name: str
    locale: str | None = None
    tags: list[str] = Field(default_factory=list)


class TTSVoiceCatalogRead(BaseModel):
    provider: str
    model: str
    target_language: str
    configured: bool
    voices: list[TTSVoiceOptionRead] = Field(default_factory=list)


router = APIRouter(tags=["p14-target-audio-voices"])


@router.get(
    "/projects/{project_id}/target-audio/voices",
    response_model=TTSVoiceCatalogRead,
)
def get_target_audio_voice_catalog_route(
    project_id: str,
    db: Session = Depends(get_db),
) -> TTSVoiceCatalogRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    provider = IndexTTS25Provider(get_settings(), target_language=project.target_language)
    voices = [TTSVoiceOptionRead.model_validate(item) for item in provider.public_voice_catalog()]
    return TTSVoiceCatalogRead(
        provider=provider.provider_name,
        model=provider.model_name,
        target_language=project.target_language,
        configured=bool(voices),
        voices=voices,
    )
