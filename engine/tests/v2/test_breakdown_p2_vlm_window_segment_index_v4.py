import pytest

from scripts import run_breakdown_vlm_window_segment_index_v4 as segment


def window() -> dict:
    # Intentionally use non-contiguous Episode ordinals to prove the model-facing local index is
    # independent from frozen Episode identifiers.
    ordinals = (13, 14, 16, 20)
    return {
        "window_id": "window-0002",
        "shots": [
            {
                "revision_item_id": f"ITEM_{ordinal}",
                "ordinal": ordinal,
                "window_start_seconds": float(index - 1),
                "window_end_seconds": float(index),
            }
            for index, ordinal in enumerate(ordinals, start=1)
        ],
    }


def test_local_index_segment_maps_back_to_frozen_shots() -> None:
    value = {
        "window_summary": "公寓走廊连续对话",
        "scene_segments": [{
            "start_index": 1,
            "end_index": 4,
            "boundary_basis": "WINDOW_START",
            "location_hint": "公寓走廊",
            "interior_exterior": "INT",
            "time_of_day": "白天",
        }],
        "subject_continuity_hints": [{
            "appearance_summary": "白衣长发女性",
            "shot_indexes": [1, 3, 4],
        }],
        "prop_continuity_hints": [{
            "label": "手机",
            "shot_indexes": [2, 4],
        }],
    }

    result = segment.expand_segments(value, window())
    hints = result["shot_scene_hints"]

    assert [item["revision_item_id"] for item in hints] == [
        "ITEM_13", "ITEM_14", "ITEM_16", "ITEM_20"
    ]
    assert [item["ordinal"] for item in hints] == [13, 14, 16, 20]
    assert all(item["scene_continuity"] == "SAME" for item in hints)
    assert all(item["camera_motion_hint"] == "UNKNOWN" for item in hints)
    assert result["subject_continuity_hints"][0]["shot_ordinals"] == [13, 16, 20]
    assert result["prop_continuity_hints"][0]["shot_ordinals"] == [14, 20]


def test_video_motion_maps_local_indexes_to_frozen_shots_and_partial_output_falls_back() -> None:
    value = {
        "window_summary": "走廊连续镜头",
        "scene_segments": [{
            "start_index": 1,
            "end_index": 4,
            "boundary_basis": "WINDOW_START",
        }],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
        # Deliberately partial: temporal motion is valuable but must not hard-fail the whole run.
        "shot_motion_hints": [
            {"index": 1, "camera_motion": "静止"},
            {"index": 3, "camera_motion": "右移"},
        ],
    }

    result = segment.expand_segments(value, window())
    by_ordinal = {item["ordinal"]: item for item in result["shot_scene_hints"]}
    assert by_ordinal[13]["camera_motion_hint"] == "静止"
    assert by_ordinal[14]["camera_motion_hint"] == "UNKNOWN"
    assert by_ordinal[16]["camera_motion_hint"] == "右移"
    assert by_ordinal[20]["camera_motion_hint"] == "UNKNOWN"


def test_duplicate_or_out_of_range_motion_index_still_fails_closed() -> None:
    base = {
        "scene_segments": [{"start_index": 1, "end_index": 4, "boundary_basis": "WINDOW_START"}],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
    }
    with pytest.raises(ValueError, match="invalid/duplicate index"):
        segment.expand_segments(
            {**base, "shot_motion_hints": [
                {"index": 1, "camera_motion": "静止"},
                {"index": 1, "camera_motion": "推近"},
            ]},
            window(),
        )
    with pytest.raises(ValueError, match="invalid/duplicate index"):
        segment.expand_segments(
            {**base, "shot_motion_hints": [{"index": 5, "camera_motion": "推近"}]},
            window(),
        )


def test_direct_local_segment_boundary_becomes_real_e6_cut() -> None:
    value = {
        "window_summary": "走廊切到客厅",
        "scene_segments": [
            {
                "start_index": 1,
                "end_index": 2,
                "boundary_basis": "WINDOW_START",
                "location_hint": "公寓走廊",
                "interior_exterior": "INT",
                "time_of_day": "白天",
            },
            {
                "start_index": 3,
                "end_index": 4,
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

    assert by_ordinal[14]["scene_continuity"] == "SAME"
    assert by_ordinal[16]["scene_continuity"] == "NEW_SCENE"
    assert by_ordinal[16]["scene_basis"] == "DIRECT"
    assert by_ordinal[16]["scene"]["location_hint"] == "客厅"
    assert by_ordinal[20]["scene_continuity"] == "SAME"


def test_context_local_boundary_does_not_force_hard_cut() -> None:
    value = {
        "window_summary": "空间可能变化",
        "scene_segments": [
            {"start_index": 1, "end_index": 2, "boundary_basis": "WINDOW_START"},
            {"start_index": 3, "end_index": 4, "boundary_basis": "CONTEXT"},
        ],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
    }

    result = segment.expand_segments(value, window())
    by_ordinal = {item["ordinal"]: item for item in result["shot_scene_hints"]}
    assert by_ordinal[16]["scene_continuity"] == "UNCERTAIN"
    assert by_ordinal[16]["scene_basis"] == "CONTEXT"


@pytest.mark.parametrize(
    "segments",
    [
        [
            {"start_index": 1, "end_index": 2, "boundary_basis": "WINDOW_START"},
            {"start_index": 4, "end_index": 4, "boundary_basis": "DIRECT"},
        ],
        [
            {"start_index": 1, "end_index": 3, "boundary_basis": "WINDOW_START"},
            {"start_index": 3, "end_index": 4, "boundary_basis": "DIRECT"},
        ],
    ],
)
def test_local_segment_gap_or_overlap_fails_closed(segments: list[dict]) -> None:
    with pytest.raises(ValueError, match="cover every Window position exactly once"):
        segment.expand_segments(
            {
                "window_summary": "",
                "scene_segments": segments,
                "subject_continuity_hints": [],
                "prop_continuity_hints": [],
            },
            window(),
        )


def test_out_of_range_index_fails_with_useful_detail() -> None:
    with pytest.raises(ValueError, match=r"valid=1\.\.4"):
        segment.expand_segments(
            {
                "scene_segments": [{
                    "start_index": 1,
                    "end_index": 12,
                    "boundary_basis": "WINDOW_START",
                }],
            },
            window(),
        )


def test_prompt_exposes_only_local_indexes_not_episode_ids() -> None:
    prompt = segment._segment_prompt("zh-CN", window())

    assert "ITEM_13" not in prompt
    assert "Shot 13" not in prompt
    assert "index=1" in prompt
    assert "1..4" in prompt
    assert '"end_index":4' in prompt
    assert '"shot_motion_hints"' in prompt
    assert "不要输出 Episode 全局 Shot 编号" in prompt
