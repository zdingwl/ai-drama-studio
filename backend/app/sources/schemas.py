from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.sources.enums import SourceAssetKind, SourceDocumentFormat


class SourceAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    asset_kind: SourceAssetKind
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    immutable: bool
    created_at: datetime


class EpisodeRead(BaseModel):
    id: str
    project_id: str
    source_asset: SourceAssetRead
    episode_order: int
    duration_us: int
    width: int
    height: int
    codec_name: str
    avg_frame_rate: str
    has_audio: bool
    created_at: datetime


class EpisodeReorderRequest(BaseModel):
    episode_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "EpisodeReorderRequest":
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("episode_ids 不能重复")
        return self


class SourceDocumentRead(BaseModel):
    id: str
    project_id: str
    source_asset: SourceAssetRead
    revision: int
    document_format: SourceDocumentFormat
    encoding: str
    char_count: int
    is_current: bool
    created_at: datetime
