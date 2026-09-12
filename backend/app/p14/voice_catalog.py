from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.p14.common import _assert_replica
from app.p14.provider import OpenAICompatibleTTSProvider
from app.projects.service import get_project


class TargetVoiceOption(BaseModel):
    voice_key: str
    display_name: str
    locale: str | None = None
    tags: list[str] = Field(default_factory=list)


class TargetVoiceCatalogRead(BaseModel):
    provider: str
    model: str
    target_language: str
    configured: bool
    voices: list[TargetVoiceOption] = Field(default_factory=list)


def get_target_voice_catalog(db: Session, project_id: str) -> TargetVoiceCatalogRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    provider = OpenAICompatibleTTSProvider(get_settings())
    voices = [TargetVoiceOption(**item) for item in provider.public_voice_catalog()]
    return TargetVoiceCatalogRead(
        provider=provider.provider_name,
        model=provider.model_name,
        target_language=project.target_language,
        configured=bool(voices),
        voices=voices,
    )
