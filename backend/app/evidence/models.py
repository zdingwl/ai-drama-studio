from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class SourceEvidenceSet(Base):
    __tablename__ = "source_evidence_sets"
    __table_args__ = (
        UniqueConstraint("episode_id", "revision", name="uq_source_evidence_set_episode_revision"),
        UniqueConstraint("task_id", name="uq_source_evidence_set_task"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_video_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asr_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ocr_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sampling_hints_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AsrEvidenceSegment(Base):
    __tablename__ = "asr_evidence_segments"
    __table_args__ = (UniqueConstraint("source_evidence_set_id", "segment_number", name="uq_asr_evidence_set_segment"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_evidence_set_id: Mapped[str] = mapped_column(ForeignKey("source_evidence_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OcrEvidenceObservation(Base):
    __tablename__ = "ocr_evidence_observations"
    __table_args__ = (UniqueConstraint("source_evidence_set_id", "observation_number", name="uq_ocr_evidence_set_observation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_evidence_set_id: Mapped[str] = mapped_column(ForeignKey("source_evidence_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    observation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sample_source: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SourceDialogueUtterance(Base):
    __tablename__ = "source_dialogue_utterances"
    __table_args__ = (UniqueConstraint("source_evidence_set_id", "utterance_number", name="uq_source_dialogue_set_utterance"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_evidence_set_id: Mapped[str] = mapped_column(ForeignKey("source_evidence_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    utterance_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_segment_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SourceVisualTextSpan(Base):
    __tablename__ = "source_visual_text_spans"
    __table_args__ = (UniqueConstraint("source_evidence_set_id", "span_number", name="uq_source_visual_text_set_span"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_evidence_set_id: Mapped[str] = mapped_column(ForeignKey("source_evidence_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    span_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_observation_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ShotDialogueProjection(Base):
    __tablename__ = "shot_dialogue_projections"
    __table_args__ = (UniqueConstraint("source_dialogue_utterance_id", "shot_anchor_id", name="uq_dialogue_projection_utterance_shot"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_evidence_set_id: Mapped[str] = mapped_column(ForeignKey("source_evidence_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    source_dialogue_utterance_id: Mapped[str] = mapped_column(ForeignKey("source_dialogue_utterances.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_anchor_id: Mapped[str] = mapped_column(ForeignKey("shot_anchors.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    overlap_start_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overlap_end_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
