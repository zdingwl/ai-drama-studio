from __future__ import annotations

from engine.app.breakdown_scene_narrative_validator_v1 import validate_scene_narrative_v1


def _packet() -> dict:
    """模拟真实 Run：Scene summary 使用男女描述，而不是人物1/人物2，人物 provenance 单独存在。"""

    return {
        "schema_version": "scene-grounding-v1",
        "source_breakdown_run_id": "BREAKDOWNRUN_REAL_REGRESSION",
        "source_shot_revision_id": "SHOTREV_REAL_REGRESSION",
        "episode_id": "EPISODE_REAL_REGRESSION",
        "scene_ordinal": 2,
        "source_fingerprint": "a" * 64,
        "deterministic_title": "客厅",
        "scene_info": {
            "location": "客厅",
            "interior_exterior": "室内",
            "time_of_day": "夜晚",
            "environment": None,
        },
        "people": [
            {"ref": "P1", "display_name": "人物1", "appearance": "男性，手持手机"},
            {"ref": "P2", "display_name": "人物2", "appearance": "女性，站立说话"},
        ],
        "facts": [
            {
                "fact_id": "F0001",
                "kind": "SCENE_LOCATION",
                "shot_ordinal": None,
                "people": [],
                "text": "客厅",
            },
            {
                "fact_id": "F0002",
                "kind": "PERSON_APPEARANCE",
                "shot_ordinal": None,
                "people": ["P1"],
                "text": "男性，手持手机",
            },
            {
                "fact_id": "F0003",
                "kind": "PERSON_APPEARANCE",
                "shot_ordinal": None,
                "people": ["P2"],
                "text": "女性，站立说话",
            },
            {
                "fact_id": "F0004",
                "kind": "SCENE_BASE_SUMMARY",
                "shot_ordinal": None,
                "people": [],
                "text": "男性手持手机，女性站立说话，两人围绕手机发生争执后离开",
            },
        ],
    }


def test_real_regression_summary_auto_completes_person_support_and_allows_grounded_compression() -> None:
    candidate = {
        "scene_ordinal": 2,
        "readable_title": None,
        "story_summary": {
            "text": "人物1与人物2围绕手机发生争执后离开。",
            "support": ["F0004"],
        },
    }

    accepted, warnings = validate_scene_narrative_v1(_packet(), candidate)

    assert warnings == []
    assert accepted["story_summary"] is not None
    assert accepted["story_summary"]["text"] == "人物1与人物2围绕手机发生争执后离开。"
    assert "F0002" in accepted["story_summary"]["support"]
    assert "F0003" in accepted["story_summary"]["support"]
    assert "F0004" in accepted["story_summary"]["support"]


def test_real_regression_summary_still_rejects_unsupported_major_plot_event() -> None:
    candidate = {
        "scene_ordinal": 2,
        "readable_title": None,
        "story_summary": {
            "text": "人物1杀死人物2后离开。",
            "support": ["F0004"],
        },
    }

    accepted, warnings = validate_scene_narrative_v1(_packet(), candidate)

    assert accepted["story_summary"] is None
    assert any("杀死" in item and "新内容字符" in item for item in warnings)
