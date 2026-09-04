"""HTTP API for the unified human-review queue."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

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
from engine.app.studio_v2 import Episode, Project
from engine.app.source_drama_snapshot_v1 import load_episode_source_drama_snapshot_v1, compose_project_source_drama_snapshot_v1
from engine.app.target_dialogue_auto_review_guard_v1 import cleanup_incomplete_auto_dialogue_reviews_v1

router = APIRouter(prefix="/api", tags=["review-issues"])


class ReviewIssueStatusPatch(BaseModel):
    status: str
    resolution: Any = None


class SpeakerReviewResolutionPatch(BaseModel):
    person_key: str = Field(min_length=1, max_length=220)


def _episode_review_snapshot(project_id: str, episode_id: str) -> dict:
    # 审核专用的单集上下文，绝不作为全项目正式就绪快照发布。
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        project = session.get(Project, project_id)
        if project is None or episode is None or episode.project_id != project_id:
            raise LookupError('剧集不属于当前项目')
        name, language = project.name, project.source_language
    snapshot = load_episode_source_drama_snapshot_v1(episode_id, infer_speakers=False)
    if snapshot is None:
        raise SourceDramaSnapshotError('当前剧集没有有效拉片结果，请先完成本集拉片')
    return compose_project_source_drama_snapshot_v1(project_id=project_id, project_name=name, source_language=language, episodes=[snapshot])


@router.post('/projects/{project_id}/episodes/{episode_id}/speaker-reviews/prepare')
def api_prepare_episode_speaker_reviews(project_id: str, episode_id: str):
    """用户明确请求审核时补齐本集任务；唯一 source_key 保证重复调用不重复建单。"""
    try:
        snapshot = _episode_review_snapshot(project_id, episode_id)
        sync_source_drama_speaker_issues(project_id, snapshot, episode_scope=True, require_explicit_speakers=True)
        return [item for item in list_review_issues(project_id, status='OPEN') if item['episode_id'] == episode_id and item['issue_type'] == 'SPEAKER']
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (SourceDramaSnapshotError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


def _find_source_dialogue_for_issue(
    snapshot: dict[str, Any],
    *,
    source_key: str,
    episode_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    dialogue_key = source_key.removeprefix(SPEAKER_PREFIX)
    for episode in snapshot.get("episodes") or []:
        if episode_id and episode.get("episode_id") != episode_id:
            continue
        for scene in episode.get("scenes") or []:
            for shot in scene.get("shots") or []:
                for dialogue in shot.get("source_dialogue") or []:
                    if dialogue.get("dialogue_key") == dialogue_key:
                        return episode, scene, dialogue
    raise LookupError("这条说话人问题对应的源对白已经不存在，请刷新待确认列表")


def _require_confirmed_speaker_person(
    people: dict[str, dict[str, Any]],
    *,
    person_key: str,
) -> dict[str, Any]:
    """Only a scene person already bound to a Final Character can become dialogue truth."""

    person = people.get(person_key)
    if person is None:
        raise ValueError("所选人物不属于这条对白所在场景，请刷新后重新选择")
    character = person.get("character")
    if not isinstance(character, dict) or not str(character.get("id") or "").strip():
        raise ValueError("请先确认人物身份并绑定正式人物，再确认对白说话人")
    return person


def _legacy_speaker_context_needs_refresh(project_id: str) -> bool:
    """Detect old speaker rows without recomposing the whole project."""

    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.issue_type == "SPEAKER",
        )).all()
        for row in rows:
            try:
                suggestion = json.loads(row.ai_suggestion_json or "null")
            except (TypeError, ValueError):
                return True
            if not isinstance(suggestion, dict):
                return True
            if not isinstance(suggestion.get("candidate_people"), list):
                return True
            if not suggestion.get("episode_order") or not suggestion.get("shot_ordinal"):
                return True
        return False


def _refresh_legacy_speaker_context(project_id: str) -> bool:
    """Explicit legacy repair helper. Never call this from a GET/read path."""

    if not _legacy_speaker_context_needs_refresh(project_id):
        return False
    try:
        snapshot = load_project_source_drama_snapshot_v1(project_id)
        sync_source_drama_speaker_issues(project_id, snapshot)
        return True
    except LookupError:
        raise
    except (SourceDramaSnapshotError, RuntimeError, ValueError):
        # Legacy maintenance must not hide the queue when current source truth cannot yet be
        # recomposed. Keep old rows for a later explicit repair attempt.
        return False


@router.get("/projects/{project_id}/review-issues")
def api_list_review_issues(
    project_id: str,
    status: str | None = Query(default="OPEN"),
):
    """Read the current review queue without changing any business data."""

    try:
        return list_review_issues(project_id, status=status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/review-issues/repair-legacy")
def api_repair_legacy_review_issues(project_id: str):
    """Explicitly repair legacy review rows created by older workflow versions.

    This command intentionally contains the old migration behavior that used to run while
    merely opening Review Center. It must only execute after an explicit POST action.
    """

    try:
        character_evidence_resolved = resolve_legacy_character_evidence_issues(project_id)
        incomplete_dialogue_reviews_removed = cleanup_incomplete_auto_dialogue_reviews_v1(project_id)
        speaker_context_refreshed = _refresh_legacy_speaker_context(project_id)
        return {
            "project_id": project_id,
            "character_evidence_resolved": character_evidence_resolved,
            "incomplete_dialogue_reviews_removed": incomplete_dialogue_reviews_removed,
            "speaker_context_refreshed": speaker_context_refreshed,
            "open_issues": list_review_issues(project_id, status="OPEN"),
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceDramaSnapshotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
            source_key = issue.source_key
            if not episode_id:
                raise ValueError("说话人问题缺少 Episode 定位信息")

        snapshot = _episode_review_snapshot(project_id, episode_id)
        _episode, scene, dialogue = _find_source_dialogue_for_issue(
            snapshot,
            source_key=source_key,
            episode_id=episode_id,
        )
        person_key = payload.person_key.strip()
        people = {
            str(person.get("person_key") or ""): person
            for person in (scene.get("people") or [])
            if isinstance(person, dict)
        }
        _require_confirmed_speaker_person(people, person_key=person_key)

        upsert_source_dialogue_speaker_override_v1(
            project_id=project_id,
            episode_id=episode_id,
            dialogue=dialogue,
            person_key=person_key,
        )

        # The override is authoritative source truth. Recompose and resync instead of merely
        # toggling ReviewIssue.status, so downstream TargetDialogue/TTS sees the correction.
        updated_snapshot = _episode_review_snapshot(project_id, episode_id)
        sync_source_drama_speaker_issues(project_id, updated_snapshot, episode_scope=True, require_explicit_speakers=True)

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
