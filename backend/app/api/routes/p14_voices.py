import base64
import binascii
import hashlib
import json
from datetime import datetime
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.db.session import get_db
from app.p14.common import _assert_replica
from app.p14.models import IndexTTSVoiceMetadata
from app.p14.provider import IndexTTS25Provider
from app.projects.service import get_project


VoiceGender = Literal["UNKNOWN", "FEMALE", "MALE", "NEUTRAL"]
VoiceAgeRange = Literal["UNKNOWN", "CHILD", "TEEN", "YOUNG_ADULT", "ADULT", "MATURE", "SENIOR"]


class TTSVoiceOptionRead(BaseModel):
    voice_key: str
    default_display_name: str
    display_name: str
    preview_url: str
    locale: str | None = None
    tags: list[str] = Field(default_factory=list)
    gender: VoiceGender = "UNKNOWN"
    age_range: VoiceAgeRange = "UNKNOWN"
    style_tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    metadata_source: Literal["CATALOG", "USER"] = "CATALOG"
    metadata_stale: bool = False
    metadata_updated_at: datetime | None = None


class TTSVoiceCatalogRead(BaseModel):
    provider: str
    model: str
    target_language: str
    configured: bool
    runtime_ready: bool
    runtime_message: str
    voices: list[TTSVoiceOptionRead] = Field(default_factory=list)


class TTSVoiceMetadataWrite(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    gender: VoiceGender = "UNKNOWN"
    age_range: VoiceAgeRange = "UNKNOWN"
    style_tags: list[str] = Field(default_factory=list, max_length=8)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("display_name 不能为空")
        return normalized

    @field_validator("style_tags")
    @classmethod
    def normalize_style_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = " ".join(str(item).split())
            if not tag:
                continue
            if len(tag) > 32:
                raise ValueError("单个风格标签不能超过 32 个字符")
            key = tag.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(tag)
        if len(normalized) > 8:
            raise ValueError("风格标签最多 8 个")
        return normalized

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


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
    model_ids = {str(item.get("id")) for item in (data or []) if isinstance(item, dict) and item.get("id")}
    if provider.model_name not in model_ids:
        return False, f"IndexTTS 服务在线，但未加载 canonical model {provider.model_name}"
    return True, "IndexTTS-2.5 READY"


def _decode_reference_audio(data_url: str) -> tuple[bytes, str]:
    try:
        header, encoded = data_url.split(",", 1)
        if not header.startswith("data:audio/") or ";base64" not in header:
            raise ValueError("not an audio base64 data URL")
        mime = header[5:].split(";", 1)[0]
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考声线试听音频无效", status_code=502) from exc
    if not raw:
        raise AppError("P14_INDEXTTS_REFERENCE_INVALID", "IndexTTS 参考声线试听音频无效", status_code=502)
    return raw, mime


def _voice_source_fingerprint(provider: IndexTTS25Provider, voice_key: str) -> str:
    entry = provider.resolve_voice(voice_key)
    payload = {"voice_key": entry.voice_key, "reference_audio_url": entry.reference_audio_url}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _voice_preview_url(project_id: str, voice_key: str) -> str:
    settings = get_settings()
    return f"{settings.api_prefix.rstrip('/')}/projects/{project_id}/target-audio/voices/{quote(voice_key, safe='')}/preview"


def _public_voice_option(project_id: str, provider: IndexTTS25Provider, item: dict, metadata: IndexTTSVoiceMetadata | None) -> TTSVoiceOptionRead:
    source_fingerprint = _voice_source_fingerprint(provider, item["voice_key"])
    metadata_stale = metadata is not None and metadata.source_fingerprint != source_fingerprint
    if metadata is not None and not metadata_stale:
        style_tags = metadata.style_tags_json if isinstance(metadata.style_tags_json, list) else []
        return TTSVoiceOptionRead(
            voice_key=item["voice_key"],
            default_display_name=item["display_name"],
            display_name=metadata.display_name,
            preview_url=_voice_preview_url(project_id, item["voice_key"]),
            locale=item.get("locale"),
            tags=list(item.get("tags") or []),
            gender=metadata.gender,
            age_range=metadata.age_range,
            style_tags=[str(tag) for tag in style_tags if str(tag).strip()],
            notes=metadata.notes,
            metadata_source="USER",
            metadata_updated_at=metadata.updated_at,
        )
    return TTSVoiceOptionRead(
        voice_key=item["voice_key"],
        default_display_name=item["display_name"],
        display_name=item["display_name"],
        preview_url=_voice_preview_url(project_id, item["voice_key"]),
        locale=item.get("locale"),
        tags=list(item.get("tags") or []),
        metadata_source="CATALOG",
        metadata_stale=metadata_stale,
    )


def _voice_metadata_map(db: Session, voice_keys: list[str]) -> dict[str, IndexTTSVoiceMetadata]:
    if not voice_keys:
        return {}
    rows = db.execute(select(IndexTTSVoiceMetadata).where(IndexTTSVoiceMetadata.voice_key.in_(voice_keys))).scalars()
    return {row.voice_key: row for row in rows}


@router.get("/projects/{project_id}/target-audio/voices", response_model=TTSVoiceCatalogRead)
def get_target_audio_voice_catalog_route(project_id: str, db: Session = Depends(get_db)) -> TTSVoiceCatalogRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    provider = IndexTTS25Provider(get_settings(), target_language=project.target_language)
    catalog = provider.public_voice_catalog()
    metadata_by_key = _voice_metadata_map(db, [item["voice_key"] for item in catalog])
    voices = [_public_voice_option(project_id, provider, item, metadata_by_key.get(item["voice_key"])) for item in catalog]
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


@router.put("/projects/{project_id}/target-audio/voices/{voice_key}/metadata", response_model=TTSVoiceOptionRead)
def put_target_audio_voice_metadata_route(project_id: str, voice_key: str, command: TTSVoiceMetadataWrite, db: Session = Depends(get_db)) -> TTSVoiceOptionRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    provider = IndexTTS25Provider(get_settings(), target_language=project.target_language)
    entry = provider.resolve_voice(voice_key)
    source_fingerprint = _voice_source_fingerprint(provider, voice_key)
    row = db.get(IndexTTSVoiceMetadata, voice_key)
    if row is None:
        row = IndexTTSVoiceMetadata(
            voice_key=voice_key,
            source_fingerprint=source_fingerprint,
            display_name=command.display_name,
            gender=command.gender,
            age_range=command.age_range,
            style_tags_json=command.style_tags,
            notes=command.notes,
            updated_at=utc_now(),
        )
        db.add(row)
    else:
        row.source_fingerprint = source_fingerprint
        row.display_name = command.display_name
        row.gender = command.gender
        row.age_range = command.age_range
        row.style_tags_json = command.style_tags
        row.notes = command.notes
        row.updated_at = utc_now()
    db.commit()
    db.refresh(row)
    return _public_voice_option(
        project_id,
        provider,
        {"voice_key": entry.voice_key, "display_name": entry.display_name, "locale": entry.locale, "tags": list(entry.tags)},
        row,
    )


@router.delete("/projects/{project_id}/target-audio/voices/{voice_key}/metadata", response_model=TTSVoiceOptionRead)
def delete_target_audio_voice_metadata_route(project_id: str, voice_key: str, db: Session = Depends(get_db)) -> TTSVoiceOptionRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    provider = IndexTTS25Provider(get_settings(), target_language=project.target_language)
    entry = provider.resolve_voice(voice_key)
    row = db.get(IndexTTSVoiceMetadata, voice_key)
    if row is not None:
        db.delete(row)
        db.commit()
    return _public_voice_option(
        project_id,
        provider,
        {"voice_key": entry.voice_key, "display_name": entry.display_name, "locale": entry.locale, "tags": list(entry.tags)},
        None,
    )


@router.get("/projects/{project_id}/target-audio/voices/{voice_key}/preview", response_class=Response)
def get_target_audio_voice_preview_route(project_id: str, voice_key: str, db: Session = Depends(get_db)) -> Response:
    project = get_project(db, project_id)
    _assert_replica(project)
    provider = IndexTTS25Provider(get_settings(), target_language=project.target_language)
    provider.resolve_voice(voice_key)
    data_url, _reference_sha = provider._reference_data_url(voice_key)
    raw, mime = _decode_reference_audio(data_url)
    return Response(content=raw, media_type=mime, headers={"Cache-Control": "private, max-age=3600", "Content-Disposition": "inline"})
