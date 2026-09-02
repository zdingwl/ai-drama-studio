"""Publish only source-snapshot problems that genuinely need human judgement."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.source_dialogue_speaker_resolver_v1 import resolve_shot_dialogue_speakers_v1
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
            people_payload = [person.model_dump(mode="json") for person in scene.people]
            for shot in scene.shots:
                dialogue_payload = [dialogue.model_dump(mode="json") for dialogue in shot.source_dialogue]
                resolutions = resolve_shot_dialogue_speakers_v1(
                    dialogue_payload,
                    scene_people=people_payload,
                    shot_people=shot.people,
                    performance=[item.model_dump(mode="json") for item in shot.performance],
                )
                for dialogue, resolution in zip(shot.source_dialogue, resolutions, strict=True):
                    if resolution.status == "RESOLVED":
                        continue

                    if len(resolution.speaker_keys) > 1:
                        reason = "同一条对白仍关联多个不同人物；自动上下文判断后仍无法安全确定唯一说话人"
                    else:
                        reason = "对白已识别，但自动结合 Scene / Shot / 表演 / 相邻对白后仍无法可靠绑定说话人"

                    source_key = f"{SPEAKER_PREFIX}{dialogue.dialogue_key}"
                    active.add(source_key)
                    speaker_rows = []
                    for person_key in resolution.speaker_keys:
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
                            "automatic_resolution_method": resolution.method,
                            "automatic_resolution_reason": resolution.reason,
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
