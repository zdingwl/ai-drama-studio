from __future__ import annotations

from pathlib import Path

from engine.app.breakdown_character_bridge_v1 import (
    CharacterPresenceSignature,
    SubjectPresenceSignature,
    resolve_scene_presence_signatures_v1,
)


def _subject(subject_id: str, ordinal: int, shots: set[str]) -> SubjectPresenceSignature:
    return SubjectPresenceSignature(
        local_subject_id=subject_id,
        local_subject_ordinal=ordinal,
        local_display_name=f"匿名{ordinal}",
        scene_person_ref=f"P{ordinal}",
        shot_ids=frozenset(shots),
    )


def _character(character_id: str, name: str, shots: set[str]) -> CharacterPresenceSignature:
    return CharacterPresenceSignature(
        character_id=character_id,
        character_name=name,
        shot_ids=frozenset(shots),
    )


def test_unique_presence_signature_resolves_to_final_character() -> None:
    result = resolve_scene_presence_signatures_v1(
        subjects=[_subject("LS1", 1, {"S1", "S2"}), _subject("LS2", 2, {"S2", "S3"})],
        characters=[_character("C1", "甲", {"S1", "S2"}), _character("C2", "乙", {"S2", "S3"})],
        shot_ordinals={"S1": 1, "S2": 2, "S3": 3},
    )

    assert [(item.status, item.character_name) for item in result] == [
        ("RESOLVED", "甲"),
        ("RESOLVED", "乙"),
    ]
    assert result[0].support_shot_ordinals == [1, 2]
    assert result[1].support_shot_ordinals == [2, 3]


def test_character_extra_presence_on_zero_subject_shot_does_not_create_false_conflict() -> None:
    result = resolve_scene_presence_signatures_v1(
        subjects=[_subject("LS1", 1, {"S2"}), _subject("LS2", 2, {"S3"})],
        characters=[
            _character("C1", "甲", {"S1", "S2"}),  # S1 has no anonymous subject at all.
            _character("C2", "乙", {"S3"}),
        ],
        shot_ordinals={"S1": 1, "S2": 2, "S3": 3},
    )

    assert result[0].status == "RESOLVED"
    assert result[0].character_id == "C1"
    assert result[1].status == "RESOLVED"
    assert result[1].character_id == "C2"


def test_two_anonymous_people_with_same_signature_fail_closed() -> None:
    result = resolve_scene_presence_signatures_v1(
        subjects=[_subject("LS1", 1, {"S1", "S2"}), _subject("LS2", 2, {"S1", "S2"})],
        characters=[_character("C1", "甲", {"S1", "S2"}), _character("C2", "乙", {"S1", "S2"})],
        shot_ordinals={"S1": 1, "S2": 2},
    )

    assert all(item.status == "UNRESOLVED" for item in result)
    assert all(item.character_id is None for item in result)
    assert {item.resolution_basis for item in result} == {"ANONYMOUS_SIGNATURE_NOT_UNIQUE"}


def test_multiple_final_characters_with_same_signature_fail_closed() -> None:
    result = resolve_scene_presence_signatures_v1(
        subjects=[_subject("LS1", 1, {"S1", "S2"})],
        characters=[_character("C1", "甲", {"S1", "S2"}), _character("C2", "乙", {"S1", "S2"})],
        shot_ordinals={"S1": 1, "S2": 2},
    )

    assert result[0].status == "UNRESOLVED"
    assert result[0].resolution_basis == "FINAL_CHARACTER_SIGNATURE_NOT_UNIQUE"


def test_partial_or_conflicting_signature_is_not_guessed() -> None:
    result = resolve_scene_presence_signatures_v1(
        subjects=[_subject("LS1", 1, {"S1", "S2"})],
        characters=[_character("C1", "甲", {"S1"}), _character("C2", "乙", {"S2"})],
        shot_ordinals={"S1": 1, "S2": 2},
    )

    assert result[0].status == "UNRESOLVED"
    assert result[0].resolution_basis == "NO_MATCHING_FINAL_CHARACTER_SIGNATURE"


def test_empty_anonymous_signature_never_resolves() -> None:
    result = resolve_scene_presence_signatures_v1(
        subjects=[_subject("LS1", 1, set())],
        characters=[_character("C1", "甲", {"S1"})],
        shot_ordinals={"S1": 1},
    )

    assert result[0].status == "UNRESOLVED"
    assert result[0].resolution_basis == "NO_ANONYMOUS_SHOT_PRESENCE"


def test_loader_is_current_revision_safe_and_does_not_use_breakdown_text_as_identity() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "engine" / "app" / "breakdown_character_bridge_v1.py").read_text(encoding="utf-8")

    assert "BreakdownRun.is_current.is_(True)" in source
    assert "BreakdownRun.status.in_(_CONSUMABLE_RUN_STATUSES)" in source
    assert "BreakdownRun.source_shot_revision_id == revision.id" in source
    assert "ShotRevision.is_current.is_(True)" in source
    assert "ShotRevisionItem.revision_id == revision.id" in source
    assert "draft.source_shot_id_snapshot != item.original_shot_id" in source
    assert "current_shots.get(item.original_shot_id)" in source
    assert "ShotCharacterBinding" in source

    # Identity authority must not come from Breakdown prose or soft appearance/role hints.
    assert "appearance_summary" not in source
    assert "role_hint" not in source
    assert "TimelineEvent" not in source
    assert "content_text" not in source
    assert "nearest" not in source.lower()
