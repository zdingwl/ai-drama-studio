from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class SourceVideoSnapshotRevision(Base):
    """Typed P10 deterministic freeze revision for SOURCE_VIDEO_SNAPSHOT."""

    __tablename__ = "source_video_snapshot_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_video_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    shot_anchors_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_dialogue_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_bible_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    story_skeleton_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    rhythm_skeleton_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_shot_facts_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_characters_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_speakers_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_scenes_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_props_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
