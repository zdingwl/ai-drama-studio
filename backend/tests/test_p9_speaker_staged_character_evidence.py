from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.shot_breakdown.schemas import BoundSubjectRef
from app.source_resolution.schemas import CharacterResolutionSemantic, SpeakerResolutionSemantic
from app.source_resolution.service import _compose_characters
from app.source_resolution.service_v2 import _compose_speakers_with_staged_character_refs


def _inputs():
    episode_id = "episode-1"
    shot = SimpleNamespace(
        shot_anchor_id="shot-1",
        shot_number=1,
        start_us=0,
        end_us=1_000_000,
        bindings=SimpleNamespace(
            characters=[BoundSubjectRef(id="p7-char-a", label="人物A")],
            scenes=[],
            props=[],
        ),
        dialogue=[SimpleNamespace(utterance_id="utt-1")],
        visual_text_evidence_ids=[],
    )
    utterance = SimpleNamespace(
        id="utt-1",
        utterance_number=1,
        start_us=100_000,
        end_us=500_000,
        text="第一句",
        language="zh",
    )
    context = SimpleNamespace(
        episode=SimpleNamespace(id=episode_id),
        shot_anchors=[SimpleNamespace(id="shot-1")],
        dialogue=[utterance],
        visual_text=[],
        shot_boundary=SimpleNamespace(id="boundary-1"),
        evidence_set=SimpleNamespace(id="evidence-1"),
        source_bible_episode=SimpleNamespace(
            characters=[SimpleNamespace(character_id="p7-char-a")],
            scenes=[],
            key_props=[],
        ),
    )
    facts = SimpleNamespace(episodes=[SimpleNamespace(episode_id=episode_id, shots=[shot])])
    return SimpleNamespace(contexts=(context,), facts_content=facts)


def _characters(inputs):
    semantic = CharacterResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "lead",
                    "display_name": "人物A",
                    "confidence": 0.95,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [
                        {
                            "ref_type": "SHOT_ANCHOR",
                            "ref_id": "shot-1",
                            "episode_id": "episode-1",
                            "shot_anchor_id": "shot-1",
                            "utterance_id": None,
                            "note": "画面人物证据",
                        }
                    ],
                }
            ],
            "observations": [
                {
                    "shot_anchor_id": "shot-1",
                    "source_candidate_id": "p7-char-a",
                    "group_key": "lead",
                    "resolution_status": "RESOLVED",
                    "reason": None,
                }
            ],
        }
    )
    return _compose_characters(inputs, semantic)


def _speaker_semantic(character_id: str, *, evidence_ref_id: str) -> SpeakerResolutionSemantic:
    return SpeakerResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "voice-a",
                    "display_name": "Speaker A",
                    "aliases": [],
                    "confidence": 0.9,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [
                        {
                            "ref_type": "P9_CHARACTER",
                            "ref_id": evidence_ref_id,
                            "episode_id": "episode-1",
                            "shot_anchor_id": "shot-1",
                            "utterance_id": "utt-1",
                            "note": "与本轮 staged Character 的音画一致性",
                        }
                    ],
                    "notes": [],
                    "character_id": character_id,
                    "source_candidate_character_ids": ["p7-char-a"],
                }
            ],
            "attributions": [
                {
                    "utterance_id": "utt-1",
                    "group_key": "voice-a",
                    "resolution_status": "RESOLVED",
                    "reason": "完整 Episode 音画支持",
                }
            ],
        }
    )


def test_speaker_evidence_accepts_character_id_from_same_staged_p9_run() -> None:
    inputs = _inputs()
    characters = _characters(inputs)
    character_id = characters.entities[0].character_id

    result = _compose_speakers_with_staged_character_refs(
        inputs,
        characters,
        _speaker_semantic(character_id, evidence_ref_id=character_id),
    )

    assert len(result.entities) == 1
    assert result.entities[0].character_id == character_id
    assert result.entities[0].evidence_refs[0].ref_id == character_id
    assert result.attributions[0].speaker_id == result.entities[0].speaker_id


def test_speaker_evidence_rejects_character_id_not_in_same_staged_p9_run() -> None:
    inputs = _inputs()
    characters = _characters(inputs)
    character_id = characters.entities[0].character_id

    with pytest.raises(AppError) as captured:
        _compose_speakers_with_staged_character_refs(
            inputs,
            characters,
            _speaker_semantic(character_id, evidence_ref_id="p9-chr-not-staged"),
        )

    assert captured.value.code == "P9_EVIDENCE_REF_INVALID"
