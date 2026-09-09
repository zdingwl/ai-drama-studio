from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base
from app.projects.enums import (
    AudioPolicy,
    ProjectStatus,
    ProjectType,
    SceneStrategy,
    SourceUnderstandingProvider,
)


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
    visual_style: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_understanding_provider: Mapped[SourceUnderstandingProvider] = mapped_column(
        Enum(SourceUnderstandingProvider, native_enum=False, length=40),
        nullable=False,
        default=SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API,
    )
    root_skill_id: Mapped[str] = mapped_column(String(96), nullable=False)
    root_skill_version: Mapped[str] = mapped_column(String(32), nullable=False)
    current_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=16), nullable=False, default=ProjectStatus.ACTIVE
    )
    workflow_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
