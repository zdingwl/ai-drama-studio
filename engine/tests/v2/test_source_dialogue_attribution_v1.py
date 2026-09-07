from __future__ import annotations

from copy import deepcopy

from engine.app.source_dialogue_attribution_v1 import normalize_dorca_response_v1
from engine.app.source_dialogue_speaker_resolver_v1 import resolve_shot_dialogue_speakers_v1


def _packet() -> dict:
    return {
        "episode_id": "EP_1",
        "source_language": "zh-CN",
        "source_breakdown_run_id": "BREAKDOWN_1",
        "source_shot_revision_id": "SHOTREV_1",
        "scenes": [
            {
                "scene_ordinal": 1,
                "start_us": 0,
                "end_us": 4_000_000,
                "people": [
                    {"ref": "P1", "display_name": "人物1", "appearance": "年轻女性"},
                    {"ref": "P2", "display_name": "人物2", "appearance": "年轻男性"},
                ],
            }
        ],
        "canonical_utterances": [
            {
                "dialogue_group_id": "BREAKDOWN_1:DG:U1",
                "scene_ordinal": 1,
                "start_us": 1_000_000,
                "end_us": 2_000_000,
                "canonical_text_evidence": "你怎么会在这里？",
                "shot_ordinals": [1],
            }
        ],
    }


def _people() -> list[dict]:
    return [
        {
            "person_key": "EP_1:BREAKDOWN_1:S1:P1",
            "scene_person_ref": "P1",
            "display_name": "人物1",
            "character": {"id": "CHAR_1"},
        },
        {
            "person_key": "EP_1:BREAKDOWN_1:S1:P2",
            "scene_person_ref": "P2",
            "display_name": "人物2",
            "character": {"id": "CHAR_2"},
        },
    ]


def test_normalize_dorca_response_keeps_host_utterance_identity_and_speaker_ref() -> None:
    artifact = normalize_dorca_response_v1(
        _packet(),
        {
            "utterances": [
                {
                    "dialogue_group_id": "BREAKDOWN_1:DG:U1",
                    "speaker_ref": "P2",
                    "confidence": 0.86,
                    "mode": "ON_CAMERA",
                    "heard_text": "你怎么会在这里？",
                }
            ]
        },
        project_id="PROJECT_1",
    )

    assert artifact.status == "READY"
    assert artifact.items[0].dialogue_group_id == "BREAKDOWN_1:DG:U1"
    assert artifact.items[0].speaker_ref == "P2"
    assert artifact.items[0].heard_text == "你怎么会在这里？"
    assert len(artifact.input_fingerprint) == 64
    assert len(artifact.output_fingerprint) == 64


def test_invalid_dorca_person_ref_auto_degrades_to_unknown_without_blocking() -> None:
    artifact = normalize_dorca_response_v1(
        _packet(),
        {
            "utterances": [
                {
                    "dialogue_group_id": "BREAKDOWN_1:DG:U1",
                    "speaker_ref": "P99",
                    "confidence": 0.51,
                    "mode": "ON_CAMERA",
                }
            ]
        },
        project_id="PROJECT_1",
    )

    assert artifact.status == "READY_WITH_WARNINGS"
    assert artifact.items[0].speaker_ref is None
    assert artifact.warnings


def test_dorca_attribution_wins_over_old_explicit_or_rule_guess_and_never_changes_text() -> None:
    dialogue = {
        "dialogue_key": "EP_1:SHOTREV_1:H1:D1",
        "dialogue_group_id": "BREAKDOWN_1:DG:U1",
        "start_us": 1_000_000,
        "end_us": 2_000_000,
        "source_text": "你怎么会在这里？",
        # Simulate stale/older upstream SPEAKER evidence pointing at P1.
        "speakers": ["EP_1:BREAKDOWN_1:S1:P1"],
    }
    before = deepcopy(dialogue)

    result = resolve_shot_dialogue_speakers_v1(
        [dialogue],
        scene_people=_people(),
        shot_people=["EP_1:BREAKDOWN_1:S1:P1", "EP_1:BREAKDOWN_1:S1:P2"],
        performance=[],
        dialogue_attributions={
            "BREAKDOWN_1:DG:U1": {
                "dialogue_group_id": "BREAKDOWN_1:DG:U1",
                "speaker_ref": "P2",
                "confidence": 0.86,
                "mode": "ON_CAMERA",
            }
        },
    )

    assert result[0].status == "RESOLVED"
    assert result[0].method == "dorca-audiovisual"
    assert result[0].speaker_keys == ("EP_1:BREAKDOWN_1:S1:P2",)
    assert dialogue == before
    assert dialogue["source_text"] == "你怎么会在这里？"


def test_missing_dorca_result_preserves_existing_deterministic_fallback() -> None:
    dialogue = {
        "dialogue_key": "EP_1:SHOTREV_1:H1:D1",
        "dialogue_group_id": "BREAKDOWN_1:DG:U1",
        "start_us": 1_000_000,
        "end_us": 2_000_000,
        "source_text": "你怎么会在这里？",
        "speakers": [],
    }

    result = resolve_shot_dialogue_speakers_v1(
        [dialogue],
        scene_people=[_people()[0]],
        shot_people=["EP_1:BREAKDOWN_1:S1:P1"],
        performance=[],
        dialogue_attributions={},
    )

    assert result[0].status == "RESOLVED"
    assert result[0].method == "sole-scene-visible-person"
    assert result[0].speaker_keys == ("EP_1:BREAKDOWN_1:S1:P1",)


def test_missing_model_utterance_is_warning_not_blocking_contract_failure() -> None:
    artifact = normalize_dorca_response_v1(
        _packet(),
        {"utterances": []},
        project_id="PROJECT_1",
    )

    assert artifact.status == "READY_WITH_WARNINGS"
    assert len(artifact.items) == 1
    assert artifact.items[0].speaker_ref is None
    assert any("fallback" in warning for warning in artifact.warnings)
