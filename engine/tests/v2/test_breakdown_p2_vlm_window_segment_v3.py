import pytest

from scripts import run_breakdown_vlm_window_segment_v3 as segment


def window() -> dict:
    return {
        "window_id": "window-0001",
        "shots": [
            {
                "revision_item_id": f"ITEM_{ordinal}",
                "ordinal": ordinal,
                "window_start_seconds": float(ordinal - 1),
                "window_end_seconds": float(ordinal),
            }
            for ordinal in range(1, 5)
        ],
    }


def test_single_scene_segment_expands_to_every_frozen_shot() -> None:
    value = {
        "window_summary": "公寓走廊内连续对话",
        "scene_segments": [{
            "start_ordinal": 1,
            "end_ordinal": 4,
            "boundary_basis": "WINDOW_START",
            "location_hint": "公寓走廊",
            "interior_exterior": "INT",
            "time_of_day": "白天",
        }],
        "subject_continuity_hints": [{
            "appearance_summary": "白衣长发女性",
            "shot_ordinals": [1, 2, 3, 4],
        }],
        "prop_continuity_hints": [],
    }

    result = segment.expand_segments(value, window())

    hints = result["shot_scene_hints"]
    assert [item["revision_item_id"] for item in hints] == [
        "ITEM_1", "ITEM_2", "ITEM_3", "ITEM_4"
    ]
    assert all(item["scene_continuity"] == "SAME" for item in hints)
    assert all(item["scene"]["location_hint"] == "公寓走廊" for item in hints)
    assert result["subject_continuity_hints"][0]["shot_ordinals"] == [1, 2, 3, 4]


def test_direct_segment_boundary_becomes_e6_hard_scene_cut() -> None:
    value = {
        "window_summary": "走廊切到客厅",
        "scene_segments": [
            {
                "start_ordinal": 1,
                "end_ordinal": 2,
                "boundary_basis": "WINDOW_START",
                "location_hint": "公寓走廊",
                "interior_exterior": "INT",
                "time_of_day": "白天",
            },
            {
                "start_ordinal": 3,
                "end_ordinal": 4,
                "boundary_basis": "DIRECT",
                "location_hint": "客厅",
                "interior_exterior": "INT",
                "time_of_day": "白天",
            },
        ],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
    }

    result = segment.expand_segments(value, window())
    by_ordinal = {item["ordinal"]: item for item in result["shot_scene_hints"]}

    assert by_ordinal[2]["scene_continuity"] == "SAME"
    assert by_ordinal[3]["scene_continuity"] == "NEW_SCENE"
    assert by_ordinal[3]["scene_basis"] == "DIRECT"
    assert by_ordinal[3]["scene"]["location_hint"] == "客厅"
    assert by_ordinal[4]["scene_continuity"] == "SAME"


def test_context_only_segment_boundary_does_not_force_hard_cut() -> None:
    value = {
        "window_summary": "空间可能变化",
        "scene_segments": [
            {
                "start_ordinal": 1,
                "end_ordinal": 2,
                "boundary_basis": "WINDOW_START",
                "location_hint": "走廊",
                "interior_exterior": "INT",
                "time_of_day": "白天",
            },
            {
                "start_ordinal": 3,
                "end_ordinal": 4,
                "boundary_basis": "CONTEXT",
                "location_hint": "室内",
                "interior_exterior": "INT",
                "time_of_day": "白天",
            },
        ],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
    }

    result = segment.expand_segments(value, window())
    by_ordinal = {item["ordinal"]: item for item in result["shot_scene_hints"]}

    assert by_ordinal[3]["scene_continuity"] == "UNCERTAIN"
    assert by_ordinal[3]["scene_basis"] == "CONTEXT"


@pytest.mark.parametrize(
    "segments",
    [
        [
            {"start_ordinal": 1, "end_ordinal": 2, "boundary_basis": "WINDOW_START"},
            {"start_ordinal": 4, "end_ordinal": 4, "boundary_basis": "DIRECT"},
        ],
        [
            {"start_ordinal": 1, "end_ordinal": 3, "boundary_basis": "WINDOW_START"},
            {"start_ordinal": 3, "end_ordinal": 4, "boundary_basis": "DIRECT"},
        ],
    ],
)
def test_segment_coverage_gap_or_overlap_fails_closed(segments: list[dict]) -> None:
    with pytest.raises(ValueError, match="cover every target Shot exactly once"):
        segment.expand_segments(
            {
                "window_summary": "",
                "scene_segments": segments,
                "subject_continuity_hints": [],
                "prop_continuity_hints": [],
            },
            window(),
        )


def test_prompt_does_not_make_model_echo_frozen_revision_ids() -> None:
    prompt = segment._segment_prompt("zh-CN", window())

    assert "ITEM_1" not in prompt
    assert "ITEM_4" not in prompt
    assert "scene_segments" in prompt
    assert "不要输出 revision_item_id" in prompt
