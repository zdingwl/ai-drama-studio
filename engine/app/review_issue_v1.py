"""Unified human-review queue for the remake pipeline.

Automatic stages should not become separate pages. They either complete silently or
publish a ReviewIssue when a human decision is genuinely needed. Domain-specific APIs
remain responsible for applying the actual correction; this table records why attention
is needed and whether that issue has been resolved.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.studio_v2 import Base, Project, get_session, new_id, utcnow

OPEN_STATUSES = {"OPEN"}
FINAL_STATUSES = {"RESOLVED", "IGNORED"}
ALL_STATUSES = OPEN_STATUSES | FINAL_STATUSES
SEVERITIES = {"REVIEW", "BLOCKING"}


class ReviewIssue(Base):
    __tablename__ = "v2_review_issues"
    __table_args__ = (
        UniqueConstraint("project_id", "source_key", name="uq_v2_review_issue_project_source"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[str | None] = mapped_column(
        ForeignKey("v2_episodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    shot_id: Mapped[str | None] = mapped_column(
        ForeignKey("v2_shots.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_key: Mapped[str] = mapped_column(String(220), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="REVIEW", index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN", index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ai_suggestion_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    editable_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def serialize_review_issue(row: ReviewIssue) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "episode_id": row.episode_id,
        "shot_id": row.shot_id,
        "source_key": row.source_key,
        "issue_type": row.issue_type,
        "severity": row.severity,
        "status": row.status,
        "reason": row.reason,
        "ai_suggestion": _json(row.ai_suggestion_json),
        "editable_payload": _json(row.editable_payload_json),
        "resolution": _json(row.resolution_json),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


def upsert_review_issue(
    *,
    project_id: str,
    source_key: str,
    issue_type: str,
    reason: str,
    severity: str = "REVIEW",
    episode_id: str | None = None,
    shot_id: str | None = None,
    ai_suggestion: Any = None,
    editable_payload: Any = None,
) -> dict[str, Any]:
    severity = severity.strip().upper()
    if severity not in SEVERITIES:
        raise ValueError("severity 只支持 REVIEW / BLOCKING")
    source_key = source_key.strip()
    issue_type = issue_type.strip().upper()
    reason = reason.strip()
    if not source_key or not issue_type or not reason:
        raise ValueError("source_key / issue_type / reason 不能为空")

    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        row = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == source_key,
        ))
        now = utcnow()
        if row is None:
            row = ReviewIssue(
                id=new_id("REVIEW"),
                project_id=project_id,
                episode_id=episode_id,
                shot_id=shot_id,
                source_key=source_key,
                issue_type=issue_type,
                severity=severity,
                status="OPEN",
                reason=reason,
                ai_suggestion_json=json.dumps(ai_suggestion, ensure_ascii=False) if ai_suggestion is not None else None,
                editable_payload_json=json.dumps(editable_payload, ensure_ascii=False) if editable_payload is not None else None,
                updated_at=now,
            )
            session.add(row)
        else:
            row.episode_id = episode_id
            row.shot_id = shot_id
            row.issue_type = issue_type
            row.severity = severity
            row.reason = reason
            row.ai_suggestion_json = json.dumps(ai_suggestion, ensure_ascii=False) if ai_suggestion is not None else None
            row.editable_payload_json = json.dumps(editable_payload, ensure_ascii=False) if editable_payload is not None else None
            # If the automatic source still reports the problem, reopen it. This makes a
            # corrected upstream rerun authoritative without deleting review history.
            row.status = "OPEN"
            row.resolution_json = None
            row.resolved_at = None
            row.updated_at = now
        session.commit()
        session.refresh(row)
        return serialize_review_issue(row)


def list_review_issues(project_id: str, *, status: str | None = "OPEN") -> list[dict[str, Any]]:
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        query = select(ReviewIssue).where(ReviewIssue.project_id == project_id)
        if status:
            normalized = status.strip().upper()
            if normalized not in ALL_STATUSES:
                raise ValueError("status 只支持 OPEN / RESOLVED / IGNORED")
            query = query.where(ReviewIssue.status == normalized)
        rows = session.scalars(query.order_by(
            ReviewIssue.severity.desc(),
            ReviewIssue.created_at.asc(),
        )).all()
        return [serialize_review_issue(row) for row in rows]


def set_review_issue_status(issue_id: str, *, status: str, resolution: Any = None) -> dict[str, Any]:
    normalized = status.strip().upper()
    if normalized not in ALL_STATUSES:
        raise ValueError("status 只支持 OPEN / RESOLVED / IGNORED")
    with get_session() as session:
        row = session.get(ReviewIssue, issue_id)
        if row is None:
            raise LookupError("待确认问题不存在")
        now = utcnow()
        row.status = normalized
        row.updated_at = now
        row.resolution_json = json.dumps(resolution, ensure_ascii=False) if resolution is not None else None
        row.resolved_at = now if normalized in FINAL_STATUSES else None
        session.commit()
        session.refresh(row)
        return serialize_review_issue(row)


__all__ = [
    "ReviewIssue",
    "list_review_issues",
    "serialize_review_issue",
    "set_review_issue_status",
    "upsert_review_issue",
]
