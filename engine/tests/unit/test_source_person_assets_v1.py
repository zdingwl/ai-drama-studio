from engine.app.source_person_assets_v1 import _binding_intersection_suggestion


def test_binding_intersection_returns_unique_character_across_all_observation_shots():
    result = _binding_intersection_suggestion(
        {"SHOT_1", "SHOT_2", "SHOT_3"},
        {
            "SHOT_1": {"CHAR_A", "CHAR_B"},
            "SHOT_2": {"CHAR_A"},
            "SHOT_3": {"CHAR_A", "CHAR_C"},
        },
    )

    assert result == "CHAR_A"


def test_binding_intersection_refuses_ambiguous_people_that_always_share_shots():
    result = _binding_intersection_suggestion(
        {"SHOT_1", "SHOT_2"},
        {
            "SHOT_1": {"CHAR_A", "CHAR_B"},
            "SHOT_2": {"CHAR_A", "CHAR_B"},
        },
    )

    assert result is None


def test_binding_intersection_refuses_missing_final_binding():
    result = _binding_intersection_suggestion(
        {"SHOT_1", "SHOT_2"},
        {
            "SHOT_1": {"CHAR_A"},
            "SHOT_2": set(),
        },
    )

    assert result is None


def test_binding_intersection_refuses_empty_observation():
    assert _binding_intersection_suggestion(set(), {}) is None
