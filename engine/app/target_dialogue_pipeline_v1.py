"""Product coordinator for R5 target dialogue.

Human review is item-local. One uncertain line must not block TTS for every other READY
line. Target-character freshness is also enforced here so edited casting cannot silently
reuse an old manual target line or old target-character voice.

Automatic model/runtime failure is not human review: a REVIEW row is actionable only when
the model returned complete translation/localization/final text plus confidence. Empty or
partial AI output is removed and the automatic task fails so it can be retried.
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
from engine.app.target_dialogue_auto_review_guard_v1 import (
    cleanup_incomplete_auto_dialogue_reviews_v1,
    incomplete_auto_dialogue_review_ids_v1,
)
from engine.app.target_localization_v1 import get_target_localization_v1


class TargetDialogueAutoGenerationError(TargetDialogueError):
    """Automatic translation runtime/output failed; this is never a human review item."""


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

    # target_dialogue_v1 historically swallowed LocalQwenTextError and converted missing
    # model output into blank REVIEW rows. Guard the product boundary so infrastructure or
    # malformed-output failures never become 13/50/etc. empty forms for a human to fill.
    incomplete_ids = incomplete_auto_dialogue_review_ids_v1(text_bundle)
    if incomplete_ids:
        cleaned = cleanup_incomplete_auto_dialogue_reviews_v1(
            project_id,
            dialogue_ids=incomplete_ids,
        )
        raise TargetDialogueAutoGenerationError(
            f"目标对白自动翻译/本土化未生成完整结果（{cleaned or len(incomplete_ids)} 条）；"
            "这是本地 Qwen3-VL 调用或模型输出异常，不需要人工填写，请恢复自动模型后重新处理"
        )

    if not synthesize_audio:
        return text_bundle
    return materialize_target_dialogue_audio_v1(project_id)


__all__ = [
    "TargetDialogueAutoGenerationError",
    "invalidate_manual_dialogue_for_target_changes_v1",
    "run_target_dialogue_pipeline_v1",
    "validate_target_dialogue_dependencies_v1",
]
