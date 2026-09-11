from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReplicaTargetScriptRevision(Base):
    """Typed P12 revision storage for TARGET_SCRIPT artifacts."""

    __tablename__ = "replica_target_script_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    source_snapshot_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    adaptation_plan_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_bible_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    generated_by_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
