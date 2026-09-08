from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base
from app.projects.enums import AudioPolicy, ProjectStatus, ProjectType, SceneStrategy


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    project_type: Mapped[ProjectType] = mapped_column(
        Enum(ProjectType, native_enum=False, length=32), nullable=False, index=True
    )
    source_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_strategy: Mapped[SceneStrategy] = mapped_column(
        Enum(SceneStrategy, native_enum=False, length=16), nullable=False
    )
    audio_policy: Mapped[AudioPolicy] = mapped_column(
        Enum(AudioPolicy, native_enum=False, length=32), nullable=False
    )
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=16), nullable=False, default=ProjectStatus.ACTIVE
    )
    workflow_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
