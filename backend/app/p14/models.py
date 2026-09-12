from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class IndexTTSVoiceMetadata(Base):
    __tablename__ = "indextts_voice_metadata"

    voice_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    gender: Mapped[str] = mapped_column(String(24), nullable=False, default="UNKNOWN")
    age_range: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    style_tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaTargetAudioCandidate(Base):
    __tablename__ = "replica_target_audio_candidates"
    __table_args__ = (UniqueConstraint("generated_by_task_id", name="uq_replica_target_audio_candidate_task"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    target_script_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_bible_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    generation_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(800), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaTargetAudioRevision(Base):
    __tablename__ = "replica_target_audio_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    target_script_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_bible_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("replica_target_audio_candidates.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaTimingPlanCandidate(Base):
    __tablename__ = "replica_timing_plan_candidates"
    __table_args__ = (UniqueConstraint("generated_by_task_id", name="uq_replica_timing_plan_candidate_task"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    target_script_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_audio_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    generation_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(800), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplicaTimingPlanRevision(Base):
    __tablename__ = "replica_timing_plan_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    target_script_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_audio_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("replica_timing_plan_candidates.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_by_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
