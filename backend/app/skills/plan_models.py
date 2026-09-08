from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ProjectExecutionPlanRecord(Base):
    __tablename__ = "project_execution_plans"
    __table_args__ = (UniqueConstraint("project_id", "revision", name="uq_project_execution_plan_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    root_skill_id: Mapped[str] = mapped_column(String(96), nullable=False)
    root_skill_version: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ProjectExecutionPlanStepRecord(Base):
    __tablename__ = "project_execution_plan_steps"
    __table_args__ = (UniqueConstraint("plan_id", "position", name="uq_project_execution_plan_step_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("project_execution_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(96), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(800), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requires_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    produces_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_artifacts_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unavailable_capabilities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
