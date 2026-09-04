from engine.app.source_person_assets_v1 import _binding_intersection_suggestion
from engine.app.source_person_assets_v1 import person_observation_issue


def test_mixed_person_description_is_blocked_but_normal_appearance_is_not():
    assert person_observation_issue('男性灰卫衣，女性白上衣')
    assert person_observation_issue('男人灰衣；男人黑衣')
    assert person_observation_issue('女性，白上衣，黑裤子') is None
    assert person_observation_issue('男性，女性化的发型') is None
    assert person_observation_issue(None) is None


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
