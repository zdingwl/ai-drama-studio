from types import SimpleNamespace

from app.shot_breakdown.schemas import BoundSubjectRef
from app.source_resolution.schemas import (
    CharacterResolutionSemantic,
    PropResolutionSemantic,
    ResolutionStatus,
    SceneResolutionSemantic,
    SpeakerResolutionSemantic,
)
from app.source_resolution.service import (
    _compose_characters,
    _compose_props,
    _compose_scenes,
    _compose_speakers,
)


def _inputs():
    episode_id = "episode-1"
    shot_1 = SimpleNamespace(
        shot_anchor_id="shot-1",
        shot_number=1,
        start_us=0,
        end_us=1_000_000,
        bindings=SimpleNamespace(
            characters=[BoundSubjectRef(id="p7-char-a", label="同名角色")],
            scenes=[BoundSubjectRef(id="p7-scene-a", label="客厅")],
            props=[BoundSubjectRef(id="p7-prop-phone", label="手机")],
        ),
        dialogue=[SimpleNamespace(utterance_id="utt-1")],
        visual_text_evidence_ids=[],
    )
    shot_2 = SimpleNamespace(
        shot_anchor_id="shot-2",
        shot_number=2,
        start_us=1_000_000,
        end_us=2_000_000,
        bindings=SimpleNamespace(
            characters=[BoundSubjectRef(id="p7-char-b", label="同名角色")],
            scenes=[BoundSubjectRef(id="p7-scene-a", label="客厅")],
            props=[BoundSubjectRef(id="p7-prop-phone", label="手机")],
        ),
        dialogue=[SimpleNamespace(utterance_id="utt-2")],
        visual_text_evidence_ids=[],
    )
    utterances = [
        SimpleNamespace(id="utt-1", utterance_number=1, start_us=100_000, end_us=400_000, text="第一句", language="zh"),
        SimpleNamespace(id="utt-2", utterance_number=2, start_us=1_100_000, end_us=1_500_000, text="第二句", language="zh"),
    ]
    context = SimpleNamespace(
        episode=SimpleNamespace(id=episode_id),
        shot_anchors=[SimpleNamespace(id="shot-1"), SimpleNamespace(id="shot-2")],
        dialogue=utterances,
        visual_text=[],
        shot_boundary=SimpleNamespace(id="boundary-1"),
        evidence_set=SimpleNamespace(id="evidence-1"),
        source_bible_episode=SimpleNamespace(
            characters=[SimpleNamespace(character_id="p7-char-a"), SimpleNamespace(character_id="p7-char-b")],
            scenes=[SimpleNamespace(scene_id="p7-scene-a")],
            key_props=[SimpleNamespace(prop_id="p7-prop-phone")],
        ),
    )
    facts = SimpleNamespace(episodes=[SimpleNamespace(episode_id=episode_id, shots=[shot_1, shot_2])])
    return SimpleNamespace(contexts=(context,), facts_content=facts)


def _evidence(ref_id: str, *, shot_anchor_id: str | None = None, utterance_id: str | None = None) -> dict:
    return {
        "ref_type": "TEST_SOURCE_REF",
        "ref_id": ref_id,
        "episode_id": "episode-1",
        "shot_anchor_id": shot_anchor_id,
        "utterance_id": utterance_id,
        "note": "test evidence",
    }


def test_same_name_does_not_merge_characters_without_explicit_provider_grouping() -> None:
    inputs = _inputs()
    semantic = CharacterResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "a",
                    "display_name": "同名角色",
                    "confidence": 0.9,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [_evidence("shot-1", shot_anchor_id="shot-1")],
                },
                {
                    "group_key": "b",
                    "display_name": "同名角色",
                    "confidence": 0.9,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [_evidence("shot-2", shot_anchor_id="shot-2")],
                },
            ],
            "observations": [
                {"shot_anchor_id": "shot-1", "source_candidate_id": "p7-char-a", "group_key": "a", "resolution_status": "RESOLVED"},
                {"shot_anchor_id": "shot-2", "source_candidate_id": "p7-char-b", "group_key": "b", "resolution_status": "RESOLVED"},
            ],
        }
    )

    result = _compose_characters(inputs, semantic)

    assert len(result.entities) == 2
    assert {item.display_name for item in result.entities} == {"同名角色"}
    assert result.entities[0].character_id != result.entities[1].character_id
    assert result.observations[0].character_id != result.observations[1].character_id


def test_speaker_is_separate_from_character_and_nullable_character_link_is_first_class() -> None:
    inputs = _inputs()
    characters = _compose_characters(
        inputs,
        CharacterResolutionSemantic.model_validate(
            {
                "groups": [
                    {
                        "group_key": "lead",
                        "display_name": "人物A",
                        "confidence": 0.95,
                        "resolution_status": "RESOLVED",
                        "evidence_refs": [_evidence("shot-1", shot_anchor_id="shot-1")],
                    }
                ],
                "observations": [
                    {"shot_anchor_id": "shot-1", "source_candidate_id": "p7-char-a", "group_key": "lead", "resolution_status": "RESOLVED"},
                    {"shot_anchor_id": "shot-2", "source_candidate_id": "p7-char-b", "group_key": None, "resolution_status": "UNRESOLVED", "reason": "外观相似但证据不足"},
                ],
            }
        ),
    )
    semantic = SpeakerResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "voice-a",
                    "display_name": "Speaker A",
                    "confidence": 0.8,
                    "resolution_status": "RESOLVED",
                    "character_id": None,
                    "source_candidate_character_ids": ["p7-char-a"],
                    "evidence_refs": [_evidence("utt-1", utterance_id="utt-1")],
                }
            ],
            "attributions": [
                {"utterance_id": "utt-1", "group_key": "voice-a", "resolution_status": "RESOLVED"},
                {"utterance_id": "utt-2", "group_key": None, "resolution_status": "UNKNOWN", "reason": "无法可靠判断"},
            ],
        }
    )

    result = _compose_speakers(inputs, characters, semantic)

    assert len(result.entities) == 1
    speaker = result.entities[0]
    assert speaker.speaker_id != characters.entities[0].character_id
    assert speaker.character_id is None
    assert result.attributions[0].speaker_id == speaker.speaker_id
    assert result.attributions[0].text == "第一句"
    assert result.attributions[0].start_us == 100_000
    assert result.attributions[1].speaker_id is None
    assert result.attributions[1].resolution_status == ResolutionStatus.UNKNOWN


def test_scene_resolution_copies_authoritative_p5_times_and_merges_only_explicit_shots() -> None:
    inputs = _inputs()
    semantic = SceneResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "same-room",
                    "display_name": "王桂香家客厅",
                    "confidence": 0.99,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [_evidence("shot-1", shot_anchor_id="shot-1")],
                }
            ],
            "assignments": [
                {"shot_anchor_id": "shot-1", "source_candidate_ids": ["p7-scene-a"], "group_key": "same-room", "resolution_status": "RESOLVED"},
                {"shot_anchor_id": "shot-2", "source_candidate_ids": ["p7-scene-a"], "group_key": "same-room", "resolution_status": "RESOLVED"},
            ],
        }
    )

    result = _compose_scenes(inputs, semantic)

    assert len(result.entities) == 1
    assert result.entities[0].shot_anchor_ids == ["shot-1", "shot-2"]
    assert [(item.start_us, item.end_us) for item in result.assignments] == [(0, 1_000_000), (1_000_000, 2_000_000)]
    assert {item.scene_id for item in result.assignments} == {result.entities[0].scene_id}


def test_similar_props_remain_distinct_when_provider_keeps_instances_separate() -> None:
    inputs = _inputs()
    semantic = PropResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "phone-a",
                    "display_name": "手机",
                    "confidence": 0.85,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [_evidence("shot-1", shot_anchor_id="shot-1")],
                },
                {
                    "group_key": "phone-b",
                    "display_name": "手机",
                    "confidence": 0.85,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [_evidence("shot-2", shot_anchor_id="shot-2")],
                },
            ],
            "observations": [
                {"shot_anchor_id": "shot-1", "source_candidate_id": "p7-prop-phone", "group_key": "phone-a", "resolution_status": "RESOLVED"},
                {"shot_anchor_id": "shot-2", "source_candidate_id": "p7-prop-phone", "group_key": "phone-b", "resolution_status": "RESOLVED"},
            ],
        }
    )

    result = _compose_props(inputs, semantic)

    assert len(result.entities) == 2
    assert result.entities[0].prop_id != result.entities[1].prop_id
    assert result.observations[0].prop_id != result.observations[1].prop_id
