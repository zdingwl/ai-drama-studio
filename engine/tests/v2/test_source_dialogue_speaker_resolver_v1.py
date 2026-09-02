from __future__ import annotations

from engine.app.source_dialogue_speaker_resolver_v1 import resolve_shot_dialogue_speakers_v1


def _person(key: str, character_id: str | None) -> dict:
    return {
        "person_key": key,
        "display_name": key,
        "character": (
            {"id": character_id, "name": character_id, "cover_url": None}
            if character_id
            else None
        ),
    }


def _dialogue(key: str, speakers: list[str], start_us: int = 0, end_us: int = 1_000_000) -> dict:
    return {
        "dialogue_key": key,
        "start_us": start_us,
        "end_us": end_us,
        "source_text": key,
        "speakers": speakers,
    }


def test_missing_speaker_resolves_when_only_one_person_exists() -> None:
    rows = resolve_shot_dialogue_speakers_v1(
        [_dialogue("D1", [])],
        scene_people=[_person("P1", "CHAR_1")],
        shot_people=["P1"],
        performance=[],
    )

    assert rows[0].status == "RESOLVED"
    assert rows[0].speaker_keys == ("P1",)
    assert rows[0].method == "sole-scene-visible-person"


def test_missing_speaker_stays_ambiguous_with_multiple_people() -> None:
    rows = resolve_shot_dialogue_speakers_v1(
        [_dialogue("D1", [])],
        scene_people=[_person("P1", "CHAR_1"), _person("P2", "CHAR_2")],
        shot_people=["P1", "P2"],
        performance=[],
    )

    assert rows[0].status == "AMBIGUOUS"
    assert rows[0].speaker_keys == ()


def test_multiple_scene_refs_for_same_final_character_collapse_safely() -> None:
    rows = resolve_shot_dialogue_speakers_v1(
        [_dialogue("D1", ["P1", "P1_ALT"])],
        scene_people=[_person("P1", "CHAR_1"), _person("P1_ALT", "CHAR_1")],
        shot_people=["P1", "P1_ALT"],
        performance=[],
    )

    assert rows[0].status == "RESOLVED"
    assert rows[0].speaker_keys == ("P1",)
    assert rows[0].method == "same-final-character"


def test_performance_can_disambiguate_explicit_multiple_speakers() -> None:
    rows = resolve_shot_dialogue_speakers_v1(
        [_dialogue("D1", ["P1", "P2"])],
        scene_people=[_person("P1", "CHAR_1"), _person("P2", "CHAR_2")],
        shot_people=["P1", "P2"],
        performance=[{"text": "P2 开口回答", "people": ["P2"]}],
    )

    assert rows[0].status == "RESOLVED"
    assert rows[0].speaker_keys == ("P2",)
    assert rows[0].method == "performance-disambiguation"


def test_missing_middle_line_can_use_nearby_same_speaker_continuity() -> None:
    dialogues = [
        _dialogue("D1", ["P1"], 0, 1_000_000),
        _dialogue("D2", [], 1_300_000, 2_000_000),
        _dialogue("D3", ["P1"], 2_300_000, 3_000_000),
    ]
    rows = resolve_shot_dialogue_speakers_v1(
        dialogues,
        scene_people=[_person("P1", "CHAR_1"), _person("P2", "CHAR_2")],
        shot_people=["P1", "P2"],
        performance=[],
    )

    assert rows[1].status == "RESOLVED"
    assert rows[1].speaker_keys == ("P1",)
    assert rows[1].method == "dialogue-continuity"


def test_multiple_different_characters_without_evidence_remains_ambiguous() -> None:
    rows = resolve_shot_dialogue_speakers_v1(
        [_dialogue("D1", ["P1", "P2"])],
        scene_people=[_person("P1", "CHAR_1"), _person("P2", "CHAR_2")],
        shot_people=["P1", "P2"],
        performance=[],
    )

    assert rows[0].status == "AMBIGUOUS"
    assert rows[0].speaker_keys == ("P1", "P2")
