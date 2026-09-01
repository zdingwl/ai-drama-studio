"""Publish unresolved Character V10.1 identities into the unified review queue."""
from __future__ import annotations

import json

from sqlalchemy import select

from engine.app.content_analysis_v2 import CharacterCandidate
from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.studio_v2 import get_session, utcnow

PREFIX = "auto:character:"


def _evidence(raw: str | None) -> dict[str, object]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def sync_character_review_issues(project_id: str, run_id: str) -> int:
    with get_session() as session:
        candidates = list(session.scalars(select(CharacterCandidate).where(
            CharacterCandidate.run_id == run_id,
            CharacterCandidate.project_id == project_id,
        ).order_by(CharacterCandidate.ordinal)).all())

    active: set[str] = set()
    count = 0
    for candidate in candidates:
        evidence = _evidence(candidate.evidence_json)
        status = str(evidence.get("identity_status") or "UNRESOLVED").upper()
        if status == "RESOLVED":
            continue
        source_key = f"{PREFIX}{candidate.id}"
        active.add(source_key)
        upsert_review_issue(
            project_id=project_id,
            source_key=source_key,
            issue_type="CHARACTER_IDENTITY",
            severity="REVIEW",
            reason=f"人物候选「{candidate.auto_label}」还不能安全归属到最终人物，需要人工确认、合并或拆分",
            ai_suggestion={
                "candidate_id": candidate.id,
                "label": candidate.auto_label,
                "track_count": candidate.track_count,
                "shot_count": candidate.shot_count,
                "confidence": candidate.confidence,
                "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
                "identity_status": status,
            },
        )
        count += 1

    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.source_key.like(f"{PREFIX}%"),
        )).all()
        changed = False
        for row in rows:
            if row.source_key in active:
                continue
            row.status = "RESOLVED"
            row.resolution_json = '{"automatic":true,"reason":"人物身份已不再处于未解析状态"}'
            row.resolved_at = utcnow()
            row.updated_at = utcnow()
            changed = True
        if changed:
            session.commit()
    return count


__all__ = ["sync_character_review_issues"]
