from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ShotBoundarySet(Base):
    __tablename__ = "shot_boundary_sets"
    __table_args__ = (
        UniqueConstraint("episode_id", "revision", name="uq_shot_boundary_set_episode_revision"),
        UniqueConstraint("task_id", name="uq_shot_boundary_set_task"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_video_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detector_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ShotAnchor(Base):
    __tablename__ = "shot_anchors"
    __table_args__ = (
        UniqueConstraint("shot_boundary_set_id", "shot_number", name="uq_shot_anchor_set_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_boundary_set_id: Mapped[str] = mapped_column(
        ForeignKey("shot_boundary_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    thumbnail_relative_path: Mapped[str] = mapped_column(String(768), nullable=False)
    reference_clip_relative_path: Mapped[str] = mapped_column(String(768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
