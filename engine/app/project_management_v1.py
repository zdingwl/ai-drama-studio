"""Project management service for the rebuilt project-list page.

This module intentionally keeps the existing ``v2_projects`` table as the source of
truth for the base project fields. Page-specific metadata (redraw rules and soft
 deletion state) lives in a small sidecar table so the first rebuilt page does not
force a risky migration of the large legacy V2 schema.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from engine.app import studio_v2

REDRAW_RULE_CHARACTER = "CHARACTER"
REDRAW_RULE_SCENE = "SCENE"
REDRAW_RULE_LANGUAGE = "LANGUAGE"
REDRAW_RULES = (
    REDRAW_RULE_CHARACTER,
    REDRAW_RULE_SCENE,
    REDRAW_RULE_LANGUAGE,
)
DEFAULT_REDRAW_RULES = list(REDRAW_RULES)


class ProjectManagementBase(DeclarativeBase):
    pass


class ProjectManagementMeta(ProjectManagementBase):
    __tablename__ = "v2_project_management_meta"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    redraw_rules_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=lambda: json.dumps(DEFAULT_REDRAW_RULES),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=studio_v2.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=studio_v2.utcnow,
        onupdate=studio_v2.utcnow,
    )


def ensure_project_management_schema() -> None:
    """Create the sidecar table idempotently for existing installations."""

    ProjectManagementBase.metadata.create_all(studio_v2.ENGINE)


def _clean_required(value: str, *, field_name: str, max_length: int) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name}不能为空")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name}不能超过 {max_length} 个字符")
    return normalized


def _normalize_redraw_rules(values: Iterable[str]) -> list[str]:
    provided = [str(value or "").strip().upper() for value in values]
    invalid = sorted({value for value in provided if value not in REDRAW_RULES})
    if invalid:
        raise ValueError(f"不支持的视频重绘规则：{', '.join(invalid)}")
    selected = [rule for rule in REDRAW_RULES if rule in provided]
    if not selected:
        raise ValueError("视频重绘规则至少选择一项")
    return selected


def _decode_redraw_rules(raw: str | None) -> list[str]:
    if not raw:
        return DEFAULT_REDRAW_RULES.copy()
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_REDRAW_RULES.copy()
    if not isinstance(value, list):
        return DEFAULT_REDRAW_RULES.copy()
    try:
        return _normalize_redraw_rules(value)
    except ValueError:
        return DEFAULT_REDRAW_RULES.copy()


def _get_meta(session, project_id: str, *, create: bool = False) -> ProjectManagementMeta | None:
    meta = session.get(ProjectManagementMeta, project_id)
    if meta is None and create:
        meta = ProjectManagementMeta(project_id=project_id)
        session.add(meta)
    return meta


def _serialize_project(project: studio_v2.Project, episodes, meta: ProjectManagementMeta | None) -> dict:
    payload = studio_v2.serialize_project(project, episodes)
    payload["redraw_rules"] = _decode_redraw_rules(meta.redraw_rules_json if meta else None)
    return payload


def list_managed_projects() -> list[dict]:
    ensure_project_management_schema()
    with studio_v2.get_session() as session:
        projects = session.scalars(
            select(studio_v2.Project).order_by(studio_v2.Project.updated_at.desc())
        ).all()
        results: list[dict] = []
        for project in projects:
            meta = _get_meta(session, project.id)
            if meta is not None and meta.deleted_at is not None:
                continue
            episodes = session.scalars(
                select(studio_v2.Episode)
                .where(studio_v2.Episode.project_id == project.id)
                .order_by(studio_v2.Episode.sort_order)
            ).all()
            for episode in episodes:
                _ = episode.preprocess
                _ = episode.shots
            results.append(_serialize_project(project, episodes, meta))
        return results


def get_managed_project(project_id: str) -> dict:
    ensure_project_management_schema()
    with studio_v2.get_session() as session:
        project = session.get(studio_v2.Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        meta = _get_meta(session, project.id)
        if meta is not None and meta.deleted_at is not None:
            raise LookupError("项目不存在")
        episodes = session.scalars(
            select(studio_v2.Episode)
            .where(studio_v2.Episode.project_id == project.id)
            .order_by(studio_v2.Episode.sort_order)
        ).all()
        for episode in episodes:
            _ = episode.preprocess
            _ = episode.shots
        return _serialize_project(project, episodes, meta)


def create_managed_project(
    *,
    name: str,
    source_language: str,
    target_language: str,
    target_region: str,
    redraw_rules: Iterable[str],
) -> dict:
    ensure_project_management_schema()
    normalized_name = _clean_required(name, field_name="标题", max_length=200)
    normalized_source = _clean_required(source_language, field_name="原项目语言", max_length=32)
    normalized_target = _clean_required(target_language, field_name="目标语言", max_length=32)
    normalized_region = _clean_required(target_region, field_name="目标地区", max_length=64)
    normalized_rules = _normalize_redraw_rules(redraw_rules)

    with studio_v2.get_session() as session:
        project = studio_v2.Project(
            id=studio_v2.new_id("PROJECT"),
            name=normalized_name,
            source_language=normalized_source,
            target_language=normalized_target,
            target_region=normalized_region,
        )
        meta = ProjectManagementMeta(
            project_id=project.id,
            redraw_rules_json=json.dumps(normalized_rules, ensure_ascii=False),
        )
        session.add(project)
        session.add(meta)
        session.commit()
        session.refresh(project)
        studio_v2.project_dir(project.id).mkdir(parents=True, exist_ok=True)
        return _serialize_project(project, [], meta)


def update_managed_project(
    project_id: str,
    *,
    name: str,
    source_language: str,
    target_language: str,
    target_region: str,
    redraw_rules: Iterable[str],
) -> dict:
    ensure_project_management_schema()
    normalized_name = _clean_required(name, field_name="标题", max_length=200)
    normalized_source = _clean_required(source_language, field_name="原项目语言", max_length=32)
    normalized_target = _clean_required(target_language, field_name="目标语言", max_length=32)
    normalized_region = _clean_required(target_region, field_name="目标地区", max_length=64)
    normalized_rules = _normalize_redraw_rules(redraw_rules)

    with studio_v2.get_session() as session:
        project = session.get(studio_v2.Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        meta = _get_meta(session, project.id, create=True)
        assert meta is not None
        if meta.deleted_at is not None:
            raise LookupError("项目不存在")

        project.name = normalized_name
        project.source_language = normalized_source
        project.target_language = normalized_target
        project.target_region = normalized_region
        project.updated_at = studio_v2.utcnow()
        meta.redraw_rules_json = json.dumps(normalized_rules, ensure_ascii=False)
        meta.updated_at = studio_v2.utcnow()
        session.commit()

        episodes = session.scalars(
            select(studio_v2.Episode)
            .where(studio_v2.Episode.project_id == project.id)
            .order_by(studio_v2.Episode.sort_order)
        ).all()
        for episode in episodes:
            _ = episode.preprocess
            _ = episode.shots
        return _serialize_project(project, episodes, meta)


def soft_delete_managed_project(project_id: str) -> None:
    """Hide a project from the rebuilt UI while keeping all generated data recoverable."""

    ensure_project_management_schema()
    with studio_v2.get_session() as session:
        project = session.get(studio_v2.Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        meta = _get_meta(session, project.id, create=True)
        assert meta is not None
        if meta.deleted_at is not None:
            raise LookupError("项目不存在")
        now = studio_v2.utcnow()
        meta.deleted_at = now
        meta.updated_at = now
        project.updated_at = now
        session.commit()
