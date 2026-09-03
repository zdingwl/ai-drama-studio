from __future__ import annotations

from engine.app.breakdown_scene_timeline_assembler_v1 import assemble_scene_timeline_v1
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelineShotV1


def test_scene_timeline_projects_shot_summary_and_narrative_function() -> None:
    payload = {
        "run": {
            "id": "BREAKDOWNRUN_NARRATIVE",
            "episode_id": "EPISODE_NARRATIVE",
            "source_shot_revision_id": "SHOTREV_NARRATIVE",
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
                "summary": "人物A与人物B在走廊发生交流",
                "environment_description": "明亮的住宅走廊",
                "subjects": [
                    {
                        "id": "LOCAL_A",
                        "ordinal": 1,
                        "display_label": "人物A",
                        "appearance_summary": "年轻女性",
                    },
                    {
                        "id": "LOCAL_B",
                        "ordinal": 2,
                        "display_label": "人物B",
                        "appearance_summary": "年长女性",
                    },
                ],
                "prop_hints": [],
                "shots": [
                    {
                        "id": "SHOTDRAFT_1",
                        "scene_segment_id": "SCENESEG_1",
                        "shot_ordinal_snapshot": 1,
                        "source_start_us": 0,
                        "source_end_us": 2_000_000,
                        "summary": "人物A面带笑容看向人物B",
                        "visual_description": "人物A面部特写，微笑并看向画面右侧",
                        "narrative_function_hint": "建立人物A对人物B的友好态度",
                        "shot_type_hint": "CLOSE_UP",
                        "camera_motion_hint": "UNKNOWN",
                        "model_metadata": {"composition_hint": "面部居中，背景虚化"},
                        "source_shot_revision_item": {},
                        "subjects": [
                            {
                                "local_subject_id": "LOCAL_A",
                                "subject": {"id": "LOCAL_A", "display_label": "人物A"},
                                "activity_summary": "人物A微笑着说话",
                            }
                        ],
                        "events": [],
                        "prop_occurrences": [],
                    }
                ],
            }
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
        "evidence_links": [],
    }

    result = assemble_scene_timeline_v1(payload)
    shot = result["scenes"][0]["shots"][0]

    assert shot["summary"] == "人物1面带笑容看向人物2"
    assert shot["narrative_function"] == "建立人物1对人物2的友好态度"
    assert shot["visual_description"] == "人物1面部特写，微笑并看向画面右侧"
    assert shot["performance"] == [{"text": "人物1微笑着说话", "people": ["P1"]}]


def test_optional_shot_narrative_fields_do_not_leak_into_legacy_shape() -> None:
    shot = SceneTimelineShotV1(
        ordinal=1,
        start_us=0,
        end_us=1_000_000,
        duration_us=1_000_000,
        thumbnail_url=None,
        reference_url=None,
        visual_description="蓝色玫瑰花束",
        people=[],
        performance=[],
        dialogue=[],
        props=[],
        cinematography={"shot_type": "特写", "composition": "主体居中", "camera_motion": None},
        on_screen_text=[],
    )

    dumped = shot.model_dump(mode="json")
    assert "summary" not in dumped
    assert "narrative_function" not in dumped
