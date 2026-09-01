"""Publish only source-snapshot problems that genuinely need human judgement."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.source_drama_snapshot_contract_v1 import SourceDramaProjectSnapshotV1
from engine.app.studio_v2 import get_session, utcnow


SPEAKER_PREFIX = "auto:source-speaker:"


def _auto_resolve_missing(project_id: str, prefix: str, active_keys: set[str]) -> None:
    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.source_key.like(f"{prefix}%"),
        )).all()
        changed = False
        for row in rows:
            if row.source_key in active_keys:
                continue
            row.status = "RESOLVED"
            row.resolution_json = json.dumps(
                {"automatic": True, "reason": "当前 SourceDramaSnapshot 已不再报告此说话人问题"},
                ensure_ascii=False,
            )
            row.resolved_at = utcnow()
            row.updated_at = utcnow()
            changed = True
        if changed:
            session.commit()


def sync_source_drama_speaker_issues(
    project_id: str,
    snapshot_payload: dict[str, Any] | SourceDramaProjectSnapshotV1,
) -> int:
    snapshot = (
        snapshot_payload
        if isinstance(snapshot_payload, SourceDramaProjectSnapshotV1)
        else SourceDramaProjectSnapshotV1.model_validate(snapshot_payload)
    )
    if snapshot.project_id != project_id:
        raise ValueError("SourceDramaSnapshot 与项目不一致")

    active: set[str] = set()
    count = 0
    for episode in snapshot.episodes:
        for scene in episode.scenes:
            people_by_key = {person.person_key: person for person in scene.people}
            for shot in scene.shots:
                for dialogue in shot.source_dialogue:
                    reason: str | None = None
                    if not dialogue.speakers:
                        reason = "对白已识别，但未能可靠绑定说话人；目标 Voice / TTS / Lip Sync 前需要确认说话角色"
                    elif len(dialogue.speakers) > 1:
                        reason = "同一条对白关联多个说话人；目标语音生成前需要确认是否为重叠说话或应拆分对白"
                    if reason is None:
                        continue

                    source_key = f"{SPEAKER_PREFIX}{dialogue.dialogue_key}"
                    active.add(source_key)
                    speaker_rows = []
                    for person_key in dialogue.speakers:
                        person = people_by_key.get(person_key)
                        if person is None:
                            continue
                        speaker_rows.append({
                            "person_key": person.person_key,
                            "display_name": person.display_name,
                            "character_id": person.character.id if person.character else None,
                            "character_name": person.character.name if person.character else None,
                        })
                    upsert_review_issue(
                        project_id=project_id,
                        episode_id=episode.episode_id,
                        shot_id=shot.source_shot_id,
                        source_key=source_key,
                        issue_type="SPEAKER",
                        severity="REVIEW",
                        reason=reason,
                        ai_suggestion={
                            "dialogue_key": dialogue.dialogue_key,
                            "source_text": dialogue.source_text,
                            "current_speakers": speaker_rows,
                        },
                        editable_payload={
                            "dialogue_key": dialogue.dialogue_key,
                            "source_text": dialogue.source_text,
                            "shot_key": shot.shot_key,
                        },
                    )
                    count += 1

    _auto_resolve_missing(project_id, SPEAKER_PREFIX, active)
    return count


__all__ = ["SPEAKER_PREFIX", "sync_source_drama_speaker_issues"]
