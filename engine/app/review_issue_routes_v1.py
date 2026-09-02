"""HTTP API for the unified human-review queue."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.app.character_review_issue_sync_v1 import resolve_legacy_character_evidence_issues
from engine.app.review_issue_v1 import (
    ReviewIssue,
    list_review_issues,
    serialize_review_issue,
    set_review_issue_status,
)
from engine.app.source_dialogue_speaker_override_v1 import upsert_source_dialogue_speaker_override_v1
from engine.app.source_drama_review_issue_sync_v1 import SPEAKER_PREFIX, sync_source_drama_speaker_issues
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError, load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import get_session

router = APIRouter(prefix="/api", tags=["review-issues"])


class ReviewIssueStatusPatch(BaseModel):
    status: str
    resolution: Any = None


class SpeakerReviewResolutionPatch(BaseModel):
    person_key: str = Field(min_length=1, max_length=220)


def _find_source_dialogue_for_issue(snapshot: dict[str, Any], issue: ReviewIssue) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    dialogue_key = issue.source_key.removeprefix(SPEAKER_PREFIX)
    for episode in snapshot.get("episodes") or []:
        if issue.episode_id and episode.get("episode_id") != issue.episode_id:
            continue
        for scene in episode.get("scenes") or []:
            for shot in scene.get("shots") or []:
                for dialogue in shot.get("source_dialogue") or []:
                    if dialogue.get("dialogue_key") == dialogue_key:
                        return episode, scene, dialogue
    raise LookupError("这条说话人问题对应的源对白已经不存在，请刷新待确认列表")


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

        # Existing projects can contain old SPEAKER rows that predate the actionable review
        # payload. Refresh them from current source truth on normal OPEN-list reads so a page
        # refresh is enough to gain episode/scene/shot/dialogue/candidate context.
        if status is None or status.strip().upper() == "OPEN":
            try:
                snapshot = load_project_source_drama_snapshot_v1(project_id)
                sync_source_drama_speaker_issues(project_id, snapshot)
            except SourceDramaSnapshotError:
                pass

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


@router.patch("/review-issues/{issue_id}/speaker")
def api_resolve_speaker_review_issue(issue_id: str, payload: SpeakerReviewResolutionPatch):
    """Write the selected source speaker, rebuild source truth, then close the issue automatically."""

    try:
        with get_session() as session:
            issue = session.get(ReviewIssue, issue_id)
            if issue is None:
                raise LookupError("待确认问题不存在")
            if issue.issue_type != "SPEAKER" or not issue.source_key.startswith(SPEAKER_PREFIX):
                raise ValueError("这条待确认不是说话人问题")
            if issue.status != "OPEN":
                raise ValueError("这条说话人问题已经处理，请刷新页面")
            project_id = issue.project_id
            episode_id = issue.episode_id
            if not episode_id:
                raise ValueError("说话人问题缺少 Episode 定位信息")

        snapshot = load_project_source_drama_snapshot_v1(project_id)
        _episode, scene, dialogue = _find_source_dialogue_for_issue(snapshot, issue)
        person_key = payload.person_key.strip()
        people = {
            str(person.get("person_key") or ""): person
            for person in (scene.get("people") or [])
            if isinstance(person, dict)
        }
        if person_key not in people:
            raise ValueError("所选人物不属于这条对白所在场景，请刷新后重新选择")

        upsert_source_dialogue_speaker_override_v1(
            project_id=project_id,
            episode_id=episode_id,
            dialogue=dialogue,
            person_key=person_key,
        )

        # The override is authoritative source truth. Recompose and resync instead of merely
        # toggling ReviewIssue.status, so downstream TargetDialogue/TTS sees the correction.
        updated_snapshot = load_project_source_drama_snapshot_v1(project_id)
        sync_source_drama_speaker_issues(project_id, updated_snapshot)

        with get_session() as session:
            updated_issue = session.get(ReviewIssue, issue_id)
            if updated_issue is None:
                raise LookupError("待确认问题不存在")
            return serialize_review_issue(updated_issue)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceDramaSnapshotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
