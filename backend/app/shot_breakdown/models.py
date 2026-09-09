from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class SourceShotFactsRevision(Base):
    __tablename__ = "source_shot_facts_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id"), nullable=False, unique=True, index=True)
    source_video_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id"), nullable=False, index=True)
    source_bible_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id"), nullable=False, index=True)
    shot_anchors_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id"), nullable=False, index=True)
    source_dialogue_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
