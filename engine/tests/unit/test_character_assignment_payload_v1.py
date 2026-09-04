from engine.app.character_assets_routes_v1 import Assignment


def test_character_assignment_payload_allows_explicit_person_without_localization_box():
    payload = Assignment(
        keys=["OBS_1"],
        name="",
        character_id="CHAR_1",
        expected_revision="revision-1",
        localizations=None,
    )

    assert payload.character_id == "CHAR_1"
    assert payload.localizations is None


def test_character_assignment_payload_defaults_to_no_localization_box():
    payload = Assignment(
        keys=["OBS_1"],
        name="New Person",
        expected_revision="revision-1",
    )

    assert payload.localizations is None
