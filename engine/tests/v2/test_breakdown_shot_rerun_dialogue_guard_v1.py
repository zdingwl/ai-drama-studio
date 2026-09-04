from __future__ import annotations

from copy import deepcopy

from engine.app.breakdown_shot_rerun_dialogue_guard_v1 import (
    CROSS_SHOT_DIALOGUE_GUARD_WARNING,
    guard_cross_shot_dialogue_rerun_v1,
)


def _shot(ordinal: int, text: str, group_id: str) -> dict[str, object]:
    start = (ordinal - 1) * 1_000_000
    end = ordinal * 1_000_000
    return {
        "ordinal": ordinal,
        "start_us": start,
        "end_us": end,
        "duration_us": end - start,
        "thumbnail_url": None,
        "reference_url": None,
        "visual_description": f"Shot {ordinal}",
        "people": [],
        "performance": [],
        "dialogue": [
            {
                "dialogue_group_id": group_id,
                "start_us": start,
                "end_us": end,
                "text": text,
                "speakers": [],
            }
        ],
        "props": [],
        "cinematography": {
            "shot_type": None,
            "composition": None,
            "camera_motion": None,
        },
        "on_screen_text": [],
    }


def _timeline() -> dict[str, object]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "RUN_1",
        "source_shot_revision_id": "REV_1",
        "episode_id": "EP_1",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 2,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 2_000_000,
                "duration_us": 2_000_000,
                "title": "场景 01",
                "scene_info": {
                    "location": None,
                    "interior_exterior": None,
                    "time_of_day": None,
                    "environment": None,
                },
                "people": [],
                "story_summary": None,
                "shots": [
                    _shot(1, "完整一句对白", "DG_CROSS"),
                    _shot(2, "完整一句对白", "DG_CROSS"),
                ],
            }
        ],
    }


def test_cross_shot_group_is_restored_when_scoped_ai_changes_one_projection() -> None:
    source = _timeline()
    effective = deepcopy(source)
    effective["scenes"][0]["shots"][0]["dialogue"][0]["text"] = "单镜新识别文本"

    guarded = guard_cross_shot_dialogue_rerun_v1(source, effective)

    assert guarded["scenes"][0]["shots"][0]["dialogue"][0]["text"] == "完整一句对白"
    assert guarded["scenes"][0]["shots"][1]["dialogue"][0]["text"] == "完整一句对白"
    assert CROSS_SHOT_DIALOGUE_GUARD_WARNING in guarded["warnings"]


def test_independent_dialogue_group_can_keep_scoped_rerun_text() -> None:
    source = _timeline()
    source["scenes"][0]["shots"][1]["dialogue"][0]["dialogue_group_id"] = "DG_OTHER"
    effective = deepcopy(source)
    effective["scenes"][0]["shots"][0]["dialogue"][0]["text"] = "单镜新识别文本"

    guarded = guard_cross_shot_dialogue_rerun_v1(source, effective)

    assert guarded["scenes"][0]["shots"][0]["dialogue"][0]["text"] == "单镜新识别文本"
    assert CROSS_SHOT_DIALOGUE_GUARD_WARNING not in guarded["warnings"]
