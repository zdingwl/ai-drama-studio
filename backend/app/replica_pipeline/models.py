from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReplicaLocalizedStoryboardCandidate(Base):
    __tablename__ = "replica_localized_storyboard_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_snapshot_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    generation_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(800), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaLocalizedStoryboardRevision(Base):
    __tablename__ = "replica_localized_storyboard_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_snapshot_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("replica_localized_storyboard_candidates.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaAssetImageCandidate(Base):
    __tablename__ = "replica_asset_image_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    target_storyboard_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    generation_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(800), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaAssetImageRevision(Base):
    __tablename__ = "replica_asset_image_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    target_storyboard_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("replica_asset_image_candidates.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaH3PromptRevision(Base):
    __tablename__ = "replica_h3_prompt_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    target_storyboard_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_assets_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
