from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.core.time import utc_now
from app.db.base import Base
from app.skills.models import ArtifactType


class ArtifactNode(Base):
    __tablename__ = "artifact_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    namespace: Mapped[ArtifactNamespace] = mapped_column(
        Enum(ArtifactNamespace, native_enum=False, length=16), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(96), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(32), nullable=False)
    validity: Mapped[ArtifactValidity] = mapped_column(
        Enum(ArtifactValidity, native_enum=False, length=16), nullable=False, default=ArtifactValidity.CURRENT, index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    @property
    def type_enum(self) -> ArtifactType:
        return ArtifactType(self.artifact_type)


class ArtifactEdge(Base):
    __tablename__ = "artifact_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id: Mapped[str] = mapped_column(ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[ArtifactRelationType] = mapped_column(
        Enum(ArtifactRelationType, native_enum=False, length=32), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
