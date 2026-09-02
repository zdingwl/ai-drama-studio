"""Project-level remake policy for the localized short-drama workflow.

This is intentionally separate from ``v2_projects`` so existing local databases do not
need an ALTER TABLE migration just to adopt the new product workflow. ``create_all`` can
safely add this one-to-one table on startup.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.studio_v2 import Base, Project, get_session, utcnow

ScenePolicy = Literal["AUTO", "KEEP", "LOCALIZE"]
GenerationEngine = Literal["MINIMAX_H3_LOCAL"]

SCENE_POLICIES = {"AUTO", "KEEP", "LOCALIZE"}
GENERATION_ENGINES = {"MINIMAX_H3_LOCAL"}
DEFAULT_SCENE_POLICY = "AUTO"
DEFAULT_CHARACTER_POLICY = "LOCALIZE"
DEFAULT_GENERATION_ENGINE = "MINIMAX_H3_LOCAL"


class ProjectRemakePolicy(Base):
    __tablename__ = "v2_project_remake_policies"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("v2_projects.id", ondelete="CASCADE"), primary_key=True
    )
    scene_policy: Mapped[str] = mapped_column(String(24), nullable=False, default=DEFAULT_SCENE_POLICY)
    character_policy: Mapped[str] = mapped_column(String(24), nullable=False, default=DEFAULT_CHARACTER_POLICY)
    generation_engine: Mapped[str] = mapped_column(
        String(48), nullable=False, default=DEFAULT_GENERATION_ENGINE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


def _serialize(row: ProjectRemakePolicy) -> dict[str, Any]:
    return {
        "project_id": row.project_id,
        "scene_policy": row.scene_policy,
        "character_policy": row.character_policy,
        "generation_engine": row.generation_engine,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _default_policy(project: Project) -> dict[str, Any]:
    """Return effective defaults without creating a database row."""

    return {
        "project_id": project.id,
        "scene_policy": DEFAULT_SCENE_POLICY,
        "character_policy": DEFAULT_CHARACTER_POLICY,
        "generation_engine": DEFAULT_GENERATION_ENGINE,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def get_project_remake_policy(project_id: str, *, create_default: bool = False) -> dict[str, Any]:
    """Read the effective remake policy.

    Reads are side-effect free by default. Projects without a persisted policy receive the same
    effective defaults in memory. ``create_default=True`` remains available only for explicit
    write/maintenance flows that intentionally want to materialize the defaults.
    """

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        row = session.get(ProjectRemakePolicy, project_id)
        if row is None and create_default:
            row = ProjectRemakePolicy(project_id=project_id)
            session.add(row)
            session.commit()
            session.refresh(row)
        return _serialize(row) if row is not None else _default_policy(project)


def update_project_remake_policy(
    project_id: str,
    *,
    scene_policy: str | None = None,
    generation_engine: str | None = None,
) -> dict[str, Any]:
    if scene_policy is not None:
        scene_policy = scene_policy.strip().upper()
        if scene_policy not in SCENE_POLICIES:
            raise ValueError("scene_policy 只支持 AUTO / KEEP / LOCALIZE")
    if generation_engine is not None:
        generation_engine = generation_engine.strip().upper()
        if generation_engine not in GENERATION_ENGINES:
            raise ValueError("当前 generation_engine 只支持 MINIMAX_H3_LOCAL")

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        row = session.get(ProjectRemakePolicy, project_id)
        if row is None:
            row = ProjectRemakePolicy(project_id=project_id)
            session.add(row)
        if scene_policy is not None:
            row.scene_policy = scene_policy
        if generation_engine is not None:
            row.generation_engine = generation_engine
        # Character replacement is a product invariant for the current remake mode.
        row.character_policy = DEFAULT_CHARACTER_POLICY
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return _serialize(row)


__all__ = [
    "DEFAULT_CHARACTER_POLICY",
    "DEFAULT_GENERATION_ENGINE",
    "DEFAULT_SCENE_POLICY",
    "GENERATION_ENGINES",
    "SCENE_POLICIES",
    "ProjectRemakePolicy",
    "get_project_remake_policy",
    "update_project_remake_policy",
]
