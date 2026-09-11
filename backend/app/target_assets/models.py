from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReplicaTargetAssetsCandidate(Base):
    __tablename__ = "replica_target_assets_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_bible_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    base_target_assets_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    generated_by_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    generation_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(800), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaTargetAssetsRevision(Base):
    __tablename__ = "replica_target_assets_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    target_bible_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("replica_target_assets_candidates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    generated_by_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
