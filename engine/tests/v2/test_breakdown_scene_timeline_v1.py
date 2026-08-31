from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from engine.app.breakdown_scene_timeline_assembler_v1 import (
    SceneTimelineAssemblyError,
    assemble_scene_timeline_v1,
)
from engine.app.breakdown_scene_timeline_contract_v1 import SCENE_TIMELINE_SCHEMA_VERSION


def _fixture_payload() -> dict[str, Any]:
    """用最小 G1 Serializer 形状覆盖 G2 的关键真相边界。"""

    return {
        "run": {
            "id": "BREAKDOWNRUN_G2_FIXTURE",
            "episode_id": "EPISODE_G2_FIXTURE",
            "source_shot_revision_id": "SHOTREV_G2_FIXTURE",
            "status": "READY",
            "is_current": True,
        },
        "scene_segments": [
            {
                "id": "SCENESEG_1",
                "ordinal": 1,
                "source_start_us": 0,
                "source_end_us": 2_000_000,
                "location_hint": "公寓走廊",
                "interior_exterior": "INTERIOR",
                "time_of_day": "DAY",
                "summary": "人物A看到人物B，随后两人发生交流",
                "environment_description": "明亮的公寓走廊",
                "subjects": [
                    {
                        "id": "LOCAL_A_SEG1",
                        "ordinal": 1,
                        "display_label": "人物A",
                        "appearance_summary": "长发女性，浅色上衣",
                    },
                    {
                        "id": "LOCAL_B_SEG1",
                        "ordinal": 2,
                        "display_label": "人物B",
                        "appearance_summary": "短发男性，深色外套",
                    },
                ],
                "prop_hints": [],
                "shots": [
                    {
                        "id": "SHOTDRAFT_1",
                        "scene_segment_id": "SCENESEG_1",
                        "shot_ordinal_snapshot": 1,
                        "source_start_us": 0,
                        "source_end_us": 500_000,
                        "summary": "蓝色玫瑰花束插在玻璃花瓶中",
                        "visual_description": "蓝色玫瑰花束插在玻璃花瓶中",
                        "shot_type_hint": "CLOSE_UP",
                        "camera_motion_hint": "UNKNOWN",
                        "model_metadata": {"composition_hint": "主体居中"},
                        "source_shot_revision_item": {
                            "thumbnail_url": "/api/shot-revision-items/ITEM_1/thumbnail",
                            "reference_url": "/api/shot-revision-items/ITEM_1/reference",
                        },
                        "subjects": [],
                        "events": [],
                        "prop_occurrences": [
                            {
                                "prop_hint": {"label_hint": "蓝色玫瑰花束"},
                                "interaction_summary": None,
                            },
                            {
                                "prop_hint": {"label_hint": "玻璃花瓶"},
                                "interaction_summary": None,
                            },
                        ],
                    },
                    {
                        "id": "SHOTDRAFT_2",
                        "scene_segment_id": "SCENESEG_1",
                        "shot_ordinal_snapshot": 2,
                        "source_start_us": 500_000,
                        "source_end_us": 2_000_000,
                        "summary": "人物A走向人物B",
                        "visual_description": "人物A走向人物B",
                        "shot_type_hint": "MEDIUM",
                        "camera_motion_hint": "UNKNOWN",
                        "model_metadata": {"composition_hint": "双人构图"},
                        "source_shot_revision_item": {
                            "thumbnail_url": "/api/shot-revision-items/ITEM_2/thumbnail",
                            "reference_url": "/api/shot-revision-items/ITEM_2/reference",
                        },
                        "subjects": [
                            {
                                "local_subject_id": "LOCAL_A_SEG1",
                                "subject": {"id": "LOCAL_A_SEG1", "display_label": "人物A"},
                                "activity_summary": "人物A转头看向人物B",
                            },
                            {
                                "local_subject_id": "LOCAL_B_SEG1",
                                "subject": {"id": "LOCAL_B_SEG1", "display_label": "人物B"},
                                "activity_summary": None,
                            },
                        ],
                        "events": [
                            {
                                "id": "EVENT_ACTION",
                                "ordinal": 1,
                                "event_type": "ACTION",
                                "source_start_us": 700_000,
                                "source_end_us": 900_000,
                                "content_text": "人物B后退一步",
                                "origin": "VLM",
                                "participants": [
                                    {
                                        "local_subject_id": "LOCAL_B_SEG1",
                                        "role": "ACTOR",
                                        "subject": {"id": "LOCAL_B_SEG1"},
                                    }
                                ],
                            },
                            {
                                "id": "EVENT_DIALOGUE_ASR",
                                "ordinal": 2,
                                "event_type": "DIALOGUE",
                                "source_start_us": 900_000,
                                "source_end_us": 1_300_000,
                                "content_text": "人物A，你  怎么现在才回来？",
                                "origin": "ASR",
                                "participants": [
                                    {
                                        "local_subject_id": "LOCAL_A_SEG1",
                                        "role": "SPEAKER",
                                        "subject": {"id": "LOCAL_A_SEG1"},
                                    }
                                ],
                            },
                            {
                                "id": "EVENT_DIALOGUE_NOT_ASR",
                                "ordinal": 3,
                                "event_type": "DIALOGUE",
                                "source_start_us": 1_300_000,
                                "source_end_us": 1_400_000,
                                "content_text": "模型猜测的一句对白",
                                "origin": "VLM",
                                "participants": [],
                            },
                            {
                                "id": "EVENT_OCR",
                                "ordinal": 4,
                                "event_type": "OCR",
                                "source_start_us": 1_400_000,
                                "source_end_us": 1_600_000,
                                "content_text": "A栋  1201",
                                "origin": "OCR",
                                "participants": [],
                            },
                        ],
                        "prop_occurrences": [
                            {
                                "prop_hint": {"label_hint": "手机"},
                                "interaction_summary": "人物B手持手机",
                            }
                        ],
                    },
                ],
            },
            {
                "id": "SCENESEG_2",
                "ordinal": 2,
                "source_start_us": 2_000_000,
                "source_end_us": 3_000_000,
                "location_hint": "客厅",
                "interior_exterior": "INTERIOR",
                "time_of_day": "NIGHT",
                "summary": "人物A独自在客厅停留",
                "environment_description": None,
                # Scene2 再次叫“人物A”也必须重新从 P1 开始，不能和 Scene1 建身份关系。
                "subjects": [
                    {
                        "id": "LOCAL_A_SEG2",
                        "ordinal": 1,
                        "display_label": "人物A",
                        "appearance_summary": "穿白色外套的人",
                    }
                ],
                "prop_hints": [],
                "shots": [
                    {
                        "id": "SHOTDRAFT_3",
                        "scene_segment_id": "SCENESEG_2",
                        "shot_ordinal_snapshot": 3,
                        "source_start_us": 2_000_000,
                        "source_end_us": 3_000_000,
                        "summary": "人物A站在客厅中央",
                        "visual_description": "人物A站在客厅中央",
                        "shot_type_hint": "WIDE",
                        "camera_motion_hint": "UNKNOWN",
                        "model_metadata": {"composition_hint": "单人居中"},
                        "source_shot_revision_item": {},
                        "subjects": [
                            {
                                "local_subject_id": "LOCAL_A_SEG2",
                                "subject": {"id": "LOCAL_A_SEG2", "display_label": "人物A"},
                                "activity_summary": "人物A原地站立",
                            }
                        ],
                        "events": [],
                        "prop_occurrences": [],
                    }
                ],
            },
        ],
        "unassigned": {
            "shots": [],
            "subjects": [],
            "subject_presences": [],
            "events": [],
            "event_participants": [],
            "prop_hints": [],
            "prop_occurrences": [],
        },
        # G2 主结果必须完全忽略这一层技术 provenance。
        "evidence_links": [
            {
                "id": "EVIDENCE_SHOULD_NOT_LEAK",
                "owner_type": "SHOT_DRAFT",
                "owner_id": "SHOTDRAFT_1",
                "source_type": "VLM_OUTPUT",
            }
        ],
    }


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            keys.update(_all_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_all_keys(item))
    return keys


def test_scene_timeline_uses_g1_truth_without_exposing_debug_internals() -> None:
    result = assemble_scene_timeline_v1(_fixture_payload())

    assert result["schema_version"] == SCENE_TIMELINE_SCHEMA_VERSION
    assert result["scene_count"] == 2
    assert result["shot_count"] == 3
    assert result["status"] == "READY"

    scene1, scene2 = result["scenes"]
    assert scene1["title"] == "公寓走廊"
    assert scene1["scene_info"]["interior_exterior"] == "室内"
    assert scene1["scene_info"]["time_of_day"] == "白天"
    assert [(item["ref"], item["display_name"]) for item in scene1["people"]] == [
        ("P1", "人物1"),
        ("P2", "人物2"),
    ]
    assert scene1["story_summary"] == "人物1看到人物2，随后两人发生交流"

    # LocalSubject 的 P* 命名空间严格按 Scene 重置；Scene2.P1 不是 Scene1.P1 的身份声明。
    assert [(item["ref"], item["display_name"]) for item in scene2["people"]] == [("P1", "人物1")]
    assert scene2["story_summary"] == "人物1独自在客厅停留"

    shot1, shot2 = scene1["shots"]
    assert shot1["people"] == []
    assert shot1["visual_description"] == "蓝色玫瑰花束插在玻璃花瓶中"
    assert [item["label"] for item in shot1["props"]] == ["蓝色玫瑰花束", "玻璃花瓶"]
    assert shot1["cinematography"] == {
        "shot_type": "特写",
        "composition": "主体居中",
        "camera_motion": None,
    }
    assert shot1["thumbnail_url"].endswith("/thumbnail")
    assert shot1["reference_url"].endswith("/reference")

    assert shot2["people"] == ["P1", "P2"]
    assert {item["text"] for item in shot2["performance"]} == {
        "人物1转头看向人物2",
        "人物2后退一步",
    }
    assert shot2["props"] == [{"label": "手机", "interaction": "人物2手持手机"}]

    # ASR 是对白文本真相：即使原文包含“人物A”以及双空格，也绝不能做匿名标签替换或空白归一化。
    assert shot2["dialogue"] == [
        {
            "start_us": 900_000,
            "end_us": 1_300_000,
            "text": "人物A，你  怎么现在才回来？",
            "speakers": ["P1"],
        }
    ]
    assert "模型猜测的一句对白" not in str(shot2["dialogue"])
    assert any("非 ASR 来源对白" in item for item in result["warnings"])

    # OCR 同样原样保留，并且不会和对白合并。
    assert shot2["on_screen_text"] == [
        {"start_us": 1_400_000, "end_us": 1_600_000, "text": "A栋  1201"}
    ]

    keys = _all_keys(result)
    for forbidden_key in {
        "confidence",
        "model_metadata",
        "evidence_links",
        "cluster_key",
        "local_subject_id",
        "source_shot_revision_item_id",
        "origin",
        "provider_metadata",
    }:
        assert forbidden_key not in keys
    assert "EVIDENCE_SHOULD_NOT_LEAK" not in str(result)
    assert "LOCAL_A_SEG1" not in str(result)
    assert "LOCAL_A_SEG2" not in str(result)


def test_scene_timeline_preserves_stale_history_instead_of_publishing_new_truth() -> None:
    payload = _fixture_payload()
    payload["run"]["status"] = "STALE"
    payload["run"]["is_current"] = False

    result = assemble_scene_timeline_v1(payload)

    assert result["status"] == "STALE"
    assert result["is_current"] is False
    assert result["source_breakdown_run_id"] == "BREAKDOWNRUN_G2_FIXTURE"
    assert result["source_shot_revision_id"] == "SHOTREV_G2_FIXTURE"


def test_scene_timeline_fails_closed_on_duplicate_shot_ordinal() -> None:
    payload = deepcopy(_fixture_payload())
    payload["scene_segments"][1]["shots"][0]["shot_ordinal_snapshot"] = 2

    with pytest.raises(SceneTimelineAssemblyError, match="Shot ordinal"):
        assemble_scene_timeline_v1(payload)


def test_scene_timeline_fails_closed_when_shot_escapes_scene_range() -> None:
    payload = deepcopy(_fixture_payload())
    payload["scene_segments"][0]["shots"][1]["source_end_us"] = 2_100_000

    with pytest.raises(SceneTimelineAssemblyError, match="超出所属 Scene"):
        assemble_scene_timeline_v1(payload)
