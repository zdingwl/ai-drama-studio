from __future__ import annotations

import pytest

from engine.app import target_dialogue_pipeline_v1
from engine.app.target_dialogue_auto_review_guard_v1 import (
    incomplete_auto_dialogue_review_ids_v1,
    is_incomplete_auto_dialogue_review_v1,
)
from engine.app.target_dialogue_v1 import TargetDialogueError


def _review_dialogue(*, complete: bool, confidence: float | None = 0.45) -> dict:
    return {
        "id": "TARGETDIALOGUE_1",
        "status": "REVIEW",
        "decision_source": "AI",
        "target_character_id": "TARGETCHAR_1",
        "translated_text": "Why are you here?" if complete else None,
        "localized_text": "What are you doing here?" if complete else None,
        "final_text": "What are you doing here?" if complete else None,
        "translation_confidence": confidence if complete else None,
    }


def _install_current_source(monkeypatch) -> None:
    monkeypatch.setattr(
        target_dialogue_pipeline_v1,
        "load_project_source_drama_snapshot_v1",
        lambda project_id: {
            "project_id": project_id,
            "source_fingerprint": "a" * 64,
        },
    )


def test_complete_low_confidence_proposal_is_real_human_review() -> None:
    row = _review_dialogue(complete=True, confidence=0.45)

    assert is_incomplete_auto_dialogue_review_v1(row) is False
    assert incomplete_auto_dialogue_review_ids_v1({"dialogues": [row]}) == set()


def test_blank_ai_review_is_classified_as_automatic_generation_failure() -> None:
    row = _review_dialogue(complete=False)

    assert is_incomplete_auto_dialogue_review_v1(row) is True
    assert incomplete_auto_dialogue_review_ids_v1({"dialogues": [row]}) == {"TARGETDIALOGUE_1"}


def test_unknown_speaker_review_is_not_misclassified_as_translation_failure() -> None:
    row = _review_dialogue(complete=False)
    row["target_character_id"] = None

    assert is_incomplete_auto_dialogue_review_v1(row) is False


def test_pipeline_fails_system_run_instead_of_returning_blank_human_forms(monkeypatch) -> None:
    bundle = {
        "dialogues": [_review_dialogue(complete=False)],
        "review_count": 1,
    }
    cleaned: list[tuple[str, set[str], str]] = []
    _install_current_source(monkeypatch)

    monkeypatch.setattr(target_dialogue_pipeline_v1, "invalidate_manual_dialogue_for_target_changes_v1", lambda _project_id: 0)
    monkeypatch.setattr(target_dialogue_pipeline_v1, "generate_target_dialogue_text_v1", lambda _project_id: bundle)
    monkeypatch.setattr(
        target_dialogue_pipeline_v1,
        "cleanup_incomplete_auto_dialogue_reviews_v1",
        lambda project_id, *, dialogue_ids, source_fingerprint: cleaned.append(
            (project_id, dialogue_ids, source_fingerprint)
        ) or len(dialogue_ids),
    )

    with pytest.raises(TargetDialogueError, match="不需要人工填写"):
        target_dialogue_pipeline_v1.run_target_dialogue_pipeline_v1("PROJECT_1", synthesize_audio=False)

    assert cleaned == [("PROJECT_1", {"TARGETDIALOGUE_1"}, "a" * 64)]


def test_pipeline_keeps_complete_low_confidence_proposal_for_review(monkeypatch) -> None:
    bundle = {
        "dialogues": [_review_dialogue(complete=True, confidence=0.45)],
        "review_count": 1,
    }
    _install_current_source(monkeypatch)

    monkeypatch.setattr(target_dialogue_pipeline_v1, "invalidate_manual_dialogue_for_target_changes_v1", lambda _project_id: 0)
    monkeypatch.setattr(target_dialogue_pipeline_v1, "generate_target_dialogue_text_v1", lambda _project_id: bundle)

    result = target_dialogue_pipeline_v1.run_target_dialogue_pipeline_v1("PROJECT_1", synthesize_audio=False)

    assert result is bundle
