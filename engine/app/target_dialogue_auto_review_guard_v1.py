"""Guard TargetDialogue human review against automatic-generation failures.

A LOCALIZATION ReviewIssue is only actionable when the model produced a complete
translation proposal and the proposal itself is uncertain. Missing model output is a
system/runtime failure and must never become an empty human form.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import select

from engine.app.review_issue_v1 import ReviewIssue
from engine.app.studio_v2 import get_session, utcnow
from engine.app.target_dialogue_v1 import LOCALIZATION_REVIEW_PREFIX, TargetDialogue


def _text(value: Any) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text or None


def is_incomplete_auto_dialogue_review_v1(item: Mapping[str, Any]) -> bool:
    """Return True only for a fake review caused by missing automatic output."""

    if str(item.get("status") or "").upper() != "REVIEW":
        return False
    if str(item.get("decision_source") or "").upper() != "AI":
        return False
    # Speaker / TargetCharacter uncertainty is owned by its upstream ReviewIssue and is
    # intentionally not classified as a translation runtime failure here.
    if not item.get("target_character_id"):
        return False
    return not (
        _text(item.get("translated_text"))
        and _text(item.get("localized_text"))
        and _text(item.get("final_text"))
        and item.get("translation_confidence") is not None
    )


def incomplete_auto_dialogue_review_ids_v1(bundle: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in bundle.get("dialogues") or []:
        if not isinstance(item, Mapping) or not is_incomplete_auto_dialogue_review_v1(item):
            continue
        dialogue_id = str(item.get("id") or "").strip()
        if dialogue_id:
            result.add(dialogue_id)
    return result


def _issue_key(source_dialogue_key: str) -> str:
    digest = hashlib.sha1(source_dialogue_key.encode("utf-8")).hexdigest()[:28]
    return f"{LOCALIZATION_REVIEW_PREFIX}{digest}"


def cleanup_incomplete_auto_dialogue_reviews_v1(
    project_id: str,
    *,
    dialogue_ids: set[str] | None = None,
) -> int:
    """Remove legacy empty TargetDialogue rows and close their fake review issues.

    The filter is deliberately strict: only AI REVIEW rows with a known target character
    and incomplete generated text are removed. Complete low-confidence proposals and all
    MANUAL rows are preserved.
    """

    with get_session() as session:
        rows = list(session.scalars(select(TargetDialogue).where(
            TargetDialogue.project_id == project_id,
            TargetDialogue.status == "REVIEW",
            TargetDialogue.decision_source == "AI",
            TargetDialogue.target_character_id.is_not(None),
        )).all())
        invalid_rows = [
            row for row in rows
            if (dialogue_ids is None or row.id in dialogue_ids)
            and is_incomplete_auto_dialogue_review_v1({
                "status": row.status,
                "decision_source": row.decision_source,
                "target_character_id": row.target_character_id,
                "translated_text": row.translated_text,
                "localized_text": row.localized_text,
                "final_text": row.final_text,
                "translation_confidence": row.translation_confidence,
            })
        ]
        if not invalid_rows:
            return 0

        issue_keys = {_issue_key(row.source_dialogue_key) for row in invalid_rows}
        for row in invalid_rows:
            # These rows never represented a valid target-language business result. Deleting
            # them makes later reads truthfully report "not generated" until the automatic
            # pipeline retries, instead of reporting a fake human REVIEW state.
            session.delete(row)

        now = utcnow()
        issues = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.issue_type == "LOCALIZATION",
            ReviewIssue.source_key.in_(issue_keys),
        )).all()
        for issue in issues:
            issue.status = "RESOLVED"
            issue.resolution_json = json.dumps({
                "automatic": True,
                "reason": "旧版本把目标对白模型未产出误报为人工确认；已移出人工队列，请由自动流程重试",
            }, ensure_ascii=False)
            issue.resolved_at = now
            issue.updated_at = now

        session.commit()
        return len(invalid_rows)


__all__ = [
    "cleanup_incomplete_auto_dialogue_reviews_v1",
    "incomplete_auto_dialogue_review_ids_v1",
    "is_incomplete_auto_dialogue_review_v1",
]
