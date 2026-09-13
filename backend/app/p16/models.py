from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReplicaGenerationAttempt(Base):
    __tablename__ = "replica_generation_attempts"
    __table_args__ = (
        UniqueConstraint(
            "generation_segments_artifact_id",
            "generation_segment_id",
            "attempt_number",
            name="uq_replica_generation_attempt_segment_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    target_storyboard_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generation_segments_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_assets_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    generation_segment_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_job_id: Mapped[str] = mapped_column(ForeignKey("provider_jobs.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    prompt_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_job_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    storage_filename: Mapped[str] = mapped_column(String(320), nullable=False)
    media_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    media_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    actual_duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    codec_name: Mapped[str] = mapped_column(String(120), nullable=False)
    technical_qc_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    technical_qc_issues_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaGenerationSelectionCandidate(Base):
    __tablename__ = "replica_generation_selection_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    target_storyboard_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generation_segments_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_assets_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
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


class ReplicaGeneratedVideoRevision(Base):
    __tablename__ = "replica_generated_video_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    selection_candidate_id: Mapped[str] = mapped_column(ForeignKey("replica_generation_selection_candidates.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaGenerationSelectionRevision(Base):
    __tablename__ = "replica_generation_selection_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    generated_video_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    selection_candidate_id: Mapped[str] = mapped_column(ForeignKey("replica_generation_selection_candidates.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
