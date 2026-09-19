from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ScriptLocalizationRevision(Base):
    __tablename__ = "script_localization_revisions"
    __table_args__ = (UniqueConstraint("artifact_id", name="uq_script_localization_revision_artifact"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
