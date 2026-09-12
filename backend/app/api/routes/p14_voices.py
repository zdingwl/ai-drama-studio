import httpx
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
    runtime_ready: bool
    runtime_message: str
    voices: list[TTSVoiceOptionRead] = Field(default_factory=list)


router = APIRouter(tags=["p14-target-audio-voices"])


def _runtime_readiness(provider: IndexTTS25Provider) -> tuple[bool, str]:
    try:
        response = httpx.get(f"{provider.base_url}/models", timeout=3.0)
    except httpx.HTTPError:
        return False, "IndexTTS-2.5 服务未启动或不可达"
    if response.status_code >= 400:
        return False, f"IndexTTS-2.5 服务返回 HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return False, "IndexTTS-2.5 /models 返回了无效 JSON"
    data = payload.get("data") if isinstance(payload, dict) else None
    model_ids = {
        str(item.get("id"))
        for item in (data or [])
        if isinstance(item, dict) and item.get("id")
    }
    if provider.model_name not in model_ids:
        return False, f"IndexTTS 服务在线，但未加载 {provider.model_name}"
    return True, "IndexTTS-2.5 READY"


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
    runtime_ready, runtime_message = _runtime_readiness(provider)
    return TTSVoiceCatalogRead(
        provider=provider.provider_name,
        model=provider.model_name,
        target_language=project.target_language,
        configured=bool(voices),
        runtime_ready=runtime_ready,
        runtime_message=runtime_message,
        voices=voices,
    )
