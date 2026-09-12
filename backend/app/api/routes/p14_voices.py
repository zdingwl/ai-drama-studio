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


def _runtime_root(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized[:-3] if normalized.endswith("/v1") else normalized


def _response_excerpt(response: httpx.Response) -> str:
    content_type = str(response.headers.get("content-type") or "").lower()
    if "json" not in content_type and "text" not in content_type:
        return ""
    try:
        compact = " ".join(response.text.split())
    except Exception:
        return ""
    return compact[:240]


def _http_failure_message(prefix: str, response: httpx.Response) -> str:
    detail = _response_excerpt(response)
    suffix = f"；{detail}" if detail else ""
    if response.status_code == 502:
        return f"{prefix}返回 HTTP 502：API 外壳已响应，但 IndexTTS 模型引擎未就绪{suffix}"
    return f"{prefix}返回 HTTP {response.status_code}{suffix}"


def _runtime_readiness(provider: IndexTTS25Provider) -> tuple[bool, str]:
    root = _runtime_root(provider.base_url)
    try:
        health = httpx.get(f"{root}/health", timeout=3.0)
    except httpx.HTTPError:
        return False, "IndexTTS-2.5 服务未启动或不可达"
    if health.status_code >= 400:
        return False, _http_failure_message("IndexTTS-2.5 /health ", health)

    try:
        response = httpx.get(f"{provider.base_url}/models", timeout=3.0)
    except httpx.HTTPError:
        return False, "IndexTTS-2.5 服务已监听，但 /v1/models 不可达"
    if response.status_code >= 400:
        return False, _http_failure_message("IndexTTS-2.5 /v1/models ", response)
    try:
        payload = response.json()
    except ValueError:
        return False, "IndexTTS-2.5 /v1/models 返回了无效 JSON"
    data = payload.get("data") if isinstance(payload, dict) else None
    model_ids = {
        str(item.get("id"))
        for item in (data or [])
        if isinstance(item, dict) and item.get("id")
    }
    if provider.model_name not in model_ids:
        return False, f"IndexTTS 服务在线，但未加载 canonical model {provider.model_name}"
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
