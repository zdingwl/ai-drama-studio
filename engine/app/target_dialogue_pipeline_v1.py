"""Product coordinator for R5 target dialogue.

Human review is item-local. One uncertain line must not block TTS for every other READY
line. Target-character freshness is also enforced here so edited casting cannot silently
reuse an old manual target line or old target-character voice.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from engine.app.studio_v2 import get_session, utcnow
from engine.app.target_dialogue_v1 import (
    TargetDialogue,
    TargetDialogueError,
    TargetVoiceProfile,
    _voice_character_signature,
    generate_target_dialogue_text_v1,
    materialize_target_dialogue_audio_v1,
)
from engine.app.target_localization_v1 import get_target_localization_v1


def _current_target_signatures(project_id: str) -> dict[str, str]:
    bundle = get_target_localization_v1(project_id)
    return {
        str(item["id"]): _voice_character_signature(item)
        for item in bundle.get("target_characters") or []
        if item.get("status") == "READY" and item.get("id")
    }


def invalidate_manual_dialogue_for_target_changes_v1(project_id: str) -> int:
    """Reopen manual lines when the TargetCharacter they were written for changed."""

    current = _current_target_signatures(project_id)
    changed_target_ids: set[str] = set()
    with get_session() as session:
        voices = session.scalars(
            select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)
        ).all()
        for voice in voices:
            signature = current.get(voice.target_character_id)
            if signature is None or signature != voice.target_character_signature:
                changed_target_ids.add(voice.target_character_id)
        if not changed_target_ids:
            return 0

        rows = session.scalars(
            select(TargetDialogue).where(
                TargetDialogue.project_id == project_id,
                TargetDialogue.target_character_id.in_(changed_target_ids),
                TargetDialogue.decision_source == "MANUAL",
            )
        ).all()
        now = utcnow()
        for row in rows:
            row.status = "REVIEW"
            row.audio_status = "PENDING"
            row.audio_input_signature = None
            row.audio_path = None
            row.speech_duration_us = None
            row.error_message = "TargetCharacter changed; confirm this manual target line again"
            row.updated_at = now
        if rows:
            session.commit()
        return len(rows)


def validate_target_dialogue_dependencies_v1(project_id: str) -> None:
    """Fail closed when persisted R5 rows depend on an older TargetCharacter definition."""

    current = _current_target_signatures(project_id)
    with get_session() as session:
        voices = session.scalars(
            select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)
        ).all()
        if any(current.get(voice.target_character_id) != voice.target_character_signature for voice in voices):
            raise TargetDialogueError("TargetDialogue target-character dependency is stale; regenerate R5")
        dialogues = session.scalars(
            select(TargetDialogue).where(TargetDialogue.project_id == project_id)
        ).all()
        for dialogue in dialogues:
            if dialogue.target_character_id and dialogue.target_character_id not in current:
                raise TargetDialogueError("TargetDialogue references a TargetCharacter that is no longer READY")


def run_target_dialogue_pipeline_v1(project_id: str, *, synthesize_audio: bool = True) -> dict[str, Any]:
    invalidate_manual_dialogue_for_target_changes_v1(project_id)
    text_bundle = generate_target_dialogue_text_v1(project_id)
    if not synthesize_audio:
        return text_bundle
    return materialize_target_dialogue_audio_v1(project_id)


__all__ = [
    "invalidate_manual_dialogue_for_target_changes_v1",
    "run_target_dialogue_pipeline_v1",
    "validate_target_dialogue_dependencies_v1",
]
