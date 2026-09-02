"""HTTP API for the unified human-review queue."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from engine.app.character_review_issue_sync_v1 import resolve_legacy_character_evidence_issues
from engine.app.review_issue_v1 import list_review_issues, set_review_issue_status

router = APIRouter(prefix="/api", tags=["review-issues"])


class ReviewIssueStatusPatch(BaseModel):
    status: str
    resolution: Any = None


@router.get("/projects/{project_id}/review-issues")
def api_list_review_issues(
    project_id: str,
    status: str | None = Query(default="OPEN"),
):
    try:
        # Migration cleanup: old V10.1 raw UNRESOLVED evidence was incorrectly published
        # as human work. Close it before returning the formal Review Center queue so an
        # already-processed project is repaired simply by refreshing the page.
        resolve_legacy_character_evidence_issues(project_id)
        return list_review_issues(project_id, status=status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/review-issues/{issue_id}")
def api_set_review_issue_status(issue_id: str, payload: ReviewIssueStatusPatch):
    try:
        return set_review_issue_status(
            issue_id,
            status=payload.status,
            resolution=payload.resolution,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
