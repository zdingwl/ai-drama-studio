"""Independent script records; SourceDocument remains the single active production input.

Only SCRIPT_TO_DRAMA uses these models. A script's stable ID is not a source asset ID;
identical texts can be stored as distinct scripts and each edit appends a revision.
"""

from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class DramaShelfScript(Base):
    __tablename__ = "drama_shelf_scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    latest_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # A pointer to the production document, not the script's stored content. The
    # active revision is checked separately so edited text is never shown as built.
    active_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL"), nullable=True
    )
    active_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DramaShelfRevision(Base):
    __tablename__ = "drama_shelf_revisions"
    __table_args__ = (UniqueConstraint("script_id", "revision", name="uq_drama_shelf_script_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    script_id: Mapped[str] = mapped_column(
        ForeignKey("drama_shelf_scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Legacy source assets and explicitly activated versions may share content;
    # this reference is for migration/diagnostics, not script identity.
    source_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
