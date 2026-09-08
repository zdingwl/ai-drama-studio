from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base
from app.sources.enums import SourceAssetKind, SourceDocumentFormat


class SourceAsset(Base):
    __tablename__ = "source_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_kind", "sha256", name="uq_source_asset_project_kind_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_kind: Mapped[SourceAssetKind] = mapped_column(
        Enum(SourceAssetKind, native_enum=False, length=16), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("source_asset_id", name="uq_episode_source_asset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    episode_order: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    codec_name: Mapped[str] = mapped_column(String(64), nullable=False)
    avg_frame_rate: Mapped[str] = mapped_column(String(32), nullable=False)
    has_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    probe_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_source_document_project_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    document_format: Mapped[SourceDocumentFormat] = mapped_column(
        Enum(SourceDocumentFormat, native_enum=False, length=16), nullable=False
    )
    encoding: Mapped[str] = mapped_column(String(32), nullable=False, default="utf-8")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
