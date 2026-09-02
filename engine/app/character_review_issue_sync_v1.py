"""Keep raw Character V10.1 uncertainty out of the human Review Center.

Character V10.1 deliberately retains UNRESOLVED visual evidence so weak/partial/occluded
person observations are not lost. Those rows are evidence, not user tasks. Human review is
created later only when a concrete source/remake decision cannot continue safely.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from engine.app.review_issue_v1 import ReviewIssue
from engine.app.studio_v2 import get_session, utcnow

PREFIX = "auto:character:"


def resolve_legacy_character_evidence_issues(project_id: str) -> int:
    """Close legacy issues that incorrectly promoted raw UNRESOLVED candidates to ReviewIssue."""

    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.source_key.like(f"{PREFIX}%"),
        )).all()
        if not rows:
            return 0

        now = utcnow()
        for row in rows:
            row.status = "RESOLVED"
            row.resolution_json = json.dumps({
                "automatic": True,
                "reason": "Character V10.1 的 UNRESOLVED 仅作为内部 Evidence 保留，不再直接升级为人工待确认",
            }, ensure_ascii=False)
            row.resolved_at = now
            row.updated_at = now
        session.commit()
        return len(rows)


def sync_character_review_issues(project_id: str, run_id: str) -> int:
    """Compatibility hook used by AUTO_REMAKE_PREP_V1.

    `run_id` is intentionally retained in the public signature so the automatic workflow
    does not need a migration-only branch. New raw character evidence creates zero human
    issues; old incorrect issues are closed automatically.
    """

    _ = run_id
    resolve_legacy_character_evidence_issues(project_id)
    return 0


__all__ = ["PREFIX", "resolve_legacy_character_evidence_issues", "sync_character_review_issues"]
