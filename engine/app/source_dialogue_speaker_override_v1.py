"""Persist manual source-dialogue speaker corrections.

ReviewIssue only records that human attention is needed. A speaker correction is source truth,
so it is stored separately and applied when SourceDramaSnapshot is composed. Overrides are tied
to a stable dialogue signature so stale decisions never silently attach to changed dialogue.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.studio_v2 import Base, Episode, Project, get_session, new_id, utcnow


class SourceDialogueSpeakerOverride(Base):
    __tablename__ = "v2_source_dialogue_speaker_overrides"
    __table_args__ = (
        UniqueConstraint("project_id", "dialogue_key", name="uq_v2_source_dialogue_speaker_override"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dialogue_key: Mapped[str] = mapped_column(String(220), nullable=False)
    dialogue_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    person_key: Mapped[str] = mapped_column(String(220), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def source_dialogue_signature_v1(dialogue: Mapping[str, Any]) -> str:
    payload = {
        "dialogue_key": str(dialogue.get("dialogue_key") or ""),
        "start_us": int(dialogue.get("start_us") or 0),
        "end_us": int(dialogue.get("end_us") or 0),
        "source_text": str(dialogue.get("source_text") or ""),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_episode_source_dialogue_speaker_overrides_v1(episode_id: str) -> dict[str, dict[str, str]]:
    with get_session() as session:
        rows = session.scalars(
            select(SourceDialogueSpeakerOverride).where(SourceDialogueSpeakerOverride.episode_id == episode_id)
        ).all()
        return {
            row.dialogue_key: {
                "person_key": row.person_key,
                "dialogue_signature": row.dialogue_signature,
            }
            for row in rows
        }


def upsert_source_dialogue_speaker_override_v1(
    *,
    project_id: str,
    episode_id: str,
    dialogue: Mapping[str, Any],
    person_key: str,
) -> dict[str, str]:
    dialogue_key = str(dialogue.get("dialogue_key") or "").strip()
    person_key = person_key.strip()
    if not dialogue_key or not person_key:
        raise ValueError("dialogue_key / person_key 不能为空")
    signature = source_dialogue_signature_v1(dialogue)

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        episode = session.get(Episode, episode_id)
        if episode is None or episode.project_id != project_id:
            raise LookupError("剧集不存在")
        row = session.scalar(select(SourceDialogueSpeakerOverride).where(
            SourceDialogueSpeakerOverride.project_id == project_id,
            SourceDialogueSpeakerOverride.dialogue_key == dialogue_key,
        ))
        now = utcnow()
        if row is None:
            row = SourceDialogueSpeakerOverride(
                id=new_id("SPEAKEROVERRIDE"),
                project_id=project_id,
                episode_id=episode_id,
                dialogue_key=dialogue_key,
                dialogue_signature=signature,
                person_key=person_key,
                updated_at=now,
            )
            session.add(row)
        else:
            row.episode_id = episode_id
            row.dialogue_signature = signature
            row.person_key = person_key
            row.updated_at = now
        session.commit()
        return {
            "dialogue_key": dialogue_key,
            "dialogue_signature": signature,
            "person_key": person_key,
        }


__all__ = [
    "SourceDialogueSpeakerOverride",
    "load_episode_source_dialogue_speaker_overrides_v1",
    "source_dialogue_signature_v1",
    "upsert_source_dialogue_speaker_override_v1",
]
