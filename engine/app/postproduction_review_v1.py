"""R10 domain actions for LIP_SYNC_QC review issues.

A review issue is never closed by this module. Retrying only re-opens the authoritative
PostProductionSegment for background execution. The issue resolves automatically only after
successful current postproduction output is produced.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from engine.app.postproduction_v1 import PostProductionSegment, get_postproduction_segment_v1
from engine.app.review_issue_v1 import ReviewIssue
from engine.app.studio_v2 import get_session, utcnow


class LipSyncReviewError(RuntimeError):
    pass


def retry_lip_sync_review_v1(project_id: str, segment_id: str) -> dict:
    source_key = f"auto:lip-sync-qc:{segment_id}"
    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(PostProductionSegment).where(
            PostProductionSegment.project_id == project_id,
            PostProductionSegment.generation_segment_id == segment_id,
        ))
        if row is None:
            raise LookupError("PostProductionSegment 不存在")
        issue = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == source_key,
            ReviewIssue.status == "OPEN",
            ReviewIssue.issue_type == "LIP_SYNC_QC",
        ))
        if issue is None:
            raise LipSyncReviewError("当前分段没有待处理的 LIP_SYNC_QC 问题")
        if row.status != "REVIEW":
            raise LipSyncReviewError(f"当前后期分段状态不是 REVIEW：{row.status}")

        row.status = "READY"
        row.lip_sync_mode = "LATENTSYNC_TARGET_FACE_ROI"
        row.reason = "人工要求重新定位目标说话人；等待后台重新执行口型后期"
        row.error_message = None
        row.updated_at = now
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload.update({
            "status": row.status,
            "lip_sync_mode": row.lip_sync_mode,
            "reason": row.reason,
            "error_message": None,
            "updated_at": now.isoformat(),
        })
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        issue.updated_at = now
        session.commit()

    result = get_postproduction_segment_v1(segment_id)
    if result is None:
        raise LipSyncReviewError("重试状态写入后无法重新读取 PostProductionSegment")
    return result


__all__ = ["LipSyncReviewError", "retry_lip_sync_review_v1"]
