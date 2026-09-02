from __future__ import annotations

import pytest

from engine.app import target_dialogue_v1 as dialogue


def _context(source_key: str, source_text: str) -> dict:
    return {
        "source_dialogue_key": source_key,
        "source_text": source_text,
        "target_character_id": "TARGETCHAR_1",
        "target_speaker_name": "Emma Miller",
        "scene_title": "Living room",
        "story_summary": "Emma confronts an unexpected visitor.",
    }


def _proposal(source_key: str, *, confidence: float = 0.95) -> dict:
    return {
        "source_dialogue_key": source_key,
        "translated_text": f"Translated {source_key}",
        "localized_text": f"Localized {source_key}",
        "final_text": f"Final {source_key}",
        "confidence": confidence,
    }


def _keys_in_prompt(prompt: str, known_keys: list[str]) -> list[str]:
    return [key for key in known_keys if key in prompt]


def test_translation_batch_failure_is_split_until_each_line_succeeds(monkeypatch) -> None:
    known_keys = ["D1", "D2", "D3"]
    rows = [_context(key, f"source {key}") for key in known_keys]
    calls: list[list[str]] = []

    def fake_request(prompt: str) -> dict:
        keys = _keys_in_prompt(prompt, known_keys)
        calls.append(keys)
        if len(keys) > 1:
            raise dialogue.LocalQwenTextError("local Qwen returned invalid JSON")
        assert len(keys) == 1
        return {"dialogues": [_proposal(keys[0])]}

    monkeypatch.setattr(dialogue, "request_local_qwen_json", fake_request)

    result = dialogue._generate_translation_proposals(
        rows,
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
        name_map={"林晚": "Emma Miller"},
    )

    assert set(result) == set(known_keys)
    assert any(len(keys) > 1 for keys in calls)
    assert all(result[key]["final_text"] == f"Final {key}" for key in known_keys)


def test_single_incomplete_line_retries_then_preserves_real_diagnostic(monkeypatch) -> None:
    calls = 0

    def fake_request(_prompt: str) -> dict:
        nonlocal calls
        calls += 1
        return {"dialogues": []}

    monkeypatch.setattr(dialogue, "request_local_qwen_json", fake_request)

    with pytest.raises(dialogue.LocalQwenTextError) as exc_info:
        dialogue._generate_translation_proposals(
            [_context("D13", "你怎么会在这里？")],
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
            name_map={"林晚": "Emma Miller"},
        )

    assert calls == dialogue.TRANSLATION_SINGLE_RETRIES
    message = str(exc_info.value)
    assert "D13" in message
    assert "缺失或字段不完整" in message


def test_complete_low_confidence_output_is_business_review_not_runtime_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        dialogue,
        "request_local_qwen_json",
        lambda _prompt: {"dialogues": [_proposal("D1", confidence=0.35)]},
    )

    result = dialogue._generate_translation_proposals(
        [_context("D1", "你怎么会在这里？")],
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
        name_map={"林晚": "Emma Miller"},
    )

    assert result["D1"]["confidence"] == 0.35
