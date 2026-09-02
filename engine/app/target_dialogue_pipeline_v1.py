"""Product coordinator for current canonical TargetDialogue.

Human review is item-local. One uncertain utterance must not block TTS for every other
READY utterance. Historical TargetDialogue rows are immutable history for current-flow
purposes: dependency validation and invalidation only touch rows anchored to the current
SourceDramaSnapshot fingerprint.

Automatic model/runtime failure is not human review: a REVIEW row is actionable only when
the model returned complete translation/localization/final text plus confidence. Empty or
partial AI output is removed only from the current source version and the automatic task
fails so it can be retried.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from engine.app.local_qwen_text_v1 import LocalQwenTextError
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import get_session, utcnow
from engine.app.target_dialogue_v1 import (
    TargetDialogue,
    TargetDialogueError,
    TargetVoiceProfile,
    _voice_character_signature,
    generate_target_dialogue_text_v1,
    get_target_dialogue_v1,
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
    """Reopen only current manual utterances when their TargetCharacter changed."""

    source = load_project_source_drama_snapshot_v1(project_id)
    fingerprint = str(source["source_fingerprint"])
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
                TargetDialogue.source_fingerprint == fingerprint,
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
            row.tts_runtime_profile = None
            row.error_message = "TargetCharacter changed; confirm this manual target line again"
            row.updated_at = now
        if rows:
            session.commit()
        return len(rows)


def validate_target_dialogue_dependencies_v1(project_id: str) -> None:
    """Fail closed for current rows without allowing stale history to poison readiness."""

    source = load_project_source_drama_snapshot_v1(project_id)
    fingerprint = str(source["source_fingerprint"])
    current = _current_target_signatures(project_id)
    with get_session() as session:
        voices = session.scalars(
            select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)
        ).all()
        if any(current.get(voice.target_character_id) != voice.target_character_signature for voice in voices):
            raise TargetDialogueError("TargetDialogue target-character dependency is stale; regenerate R5")

        dialogues = session.scalars(
            select(TargetDialogue).where(
                TargetDialogue.project_id == project_id,
                TargetDialogue.source_fingerprint == fingerprint,
            )
        ).all()
        for dialogue in dialogues:
            if dialogue.target_character_id and dialogue.target_character_id not in current:
                raise TargetDialogueError("Current TargetDialogue references a TargetCharacter that is no longer READY")

    # Coverage/source-anchor validation lives in the canonical getter. It filters by the
    # current utterance key set, so historical projection-level rows remain harmless.
    get_target_dialogue_v1(project_id)


def run_target_dialogue_pipeline_v1(project_id: str, *, synthesize_audio: bool = True) -> dict[str, Any]:
    source = load_project_source_drama_snapshot_v1(project_id)
    fingerprint = str(source["source_fingerprint"])
    invalidate_manual_dialogue_for_target_changes_v1(project_id)
    try:
        text_bundle = generate_target_dialogue_text_v1(project_id)
    except LocalQwenTextError as exc:
        cleanup_incomplete_auto_dialogue_reviews_v1(
            project_id,
            source_fingerprint=fingerprint,
        )
        raise TargetDialogueAutoGenerationError(
            "目标对白自动翻译/本土化失败；系统已自动缩小批次、拆分并重试，"
            f"仍未取得完整结构化结果。模型诊断：{exc}"
        ) from exc

    # Legacy guard: older target_dialogue_v1 versions swallowed LocalQwenTextError and
    # converted missing model output into blank REVIEW rows. Clean only current rows;
    # historical results are not rewritten by current task execution.
    incomplete_ids = incomplete_auto_dialogue_review_ids_v1(text_bundle)
    if incomplete_ids:
        cleaned = cleanup_incomplete_auto_dialogue_reviews_v1(
            project_id,
            dialogue_ids=incomplete_ids,
            source_fingerprint=fingerprint,
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
