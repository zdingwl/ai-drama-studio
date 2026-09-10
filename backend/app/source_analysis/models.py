from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class SourceStoryboardDraftRevision(Base):
    """Non-formal working copy for user storyboard edits.

    This row is deliberately not an ArtifactNode and never changes SOURCE_SHOT_FACTS.
    A future formal Target Storyboard skill may consume a selected working draft.
    """

    __tablename__ = "source_storyboard_draft_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_source_storyboard_draft_project_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_snapshot_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    overrides_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
