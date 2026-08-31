from __future__ import annotations

import json
from typing import Any

from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM
from engine.app.breakdown_scene_narrative_v1 import organize_scene_timeline_narrative_v1


def _timeline() -> dict[str, Any]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "BREAKDOWNRUN_G2_QWEN_FIXTURE",
        "source_shot_revision_id": "SHOTREV_G2_QWEN_FIXTURE",
        "episode_id": "EPISODE_G2_QWEN_FIXTURE",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 1,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 1_000_000,
                "duration_us": 1_000_000,
                "title": "公寓走廊",
                "scene_info": {
                    "location": "公寓走廊",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": None,
                },
                "people": [
                    {"ref": "P1", "display_name": "人物1", "appearance": "穿浅色上衣的人"}
                ],
                "story_summary": "人物1停留在公寓走廊",
                "shots": [
                    {
                        "ordinal": 1,
                        "start_us": 0,
                        "end_us": 1_000_000,
                        "duration_us": 1_000_000,
                        "thumbnail_url": None,
                        "reference_url": None,
                        "visual_description": "人物1站在公寓走廊",
                        "people": ["P1"],
                        "performance": [{"text": "人物1原地站立", "people": ["P1"]}],
                        "dialogue": [],
                        "props": [],
                        "cinematography": {
                            "shot_type": "中景",
                            "composition": "单人居中",
                            "camera_motion": None,
                        },
                        "on_screen_text": [],
                    }
                ],
            }
        ],
    }


def test_local_qwen_adapter_batches_scene_requests_without_real_model() -> None:
    calls: list[tuple[Any, tuple[dict[str, Any], ...]]] = []

    def fake_runner(config: Any, requests: Any) -> dict[int, str]:
        request_tuple = tuple(dict(item) for item in requests)
        calls.append((config, request_tuple))
        assert len(request_tuple) == 1
        request = request_tuple[0]
        serialized = request["user_prompt"].split("<SCENE_DATA>\n", 1)[1].rsplit("\n</SCENE_DATA>", 1)[0]
        packet = json.loads(serialized)
        location = next(item for item in packet["facts"] if item["kind"] == "SCENE_LOCATION")
        summary = next(item for item in packet["facts"] if item["kind"] == "SCENE_BASE_SUMMARY")
        return {
            int(request["scene_ordinal"]): json.dumps(
                {
                    "scene_ordinal": int(request["scene_ordinal"]),
                    "readable_title": {
                        "text": "公寓走廊",
                        "support": [location["fact_id"]],
                    },
                    "story_summary": {
                        "text": "人物1停留在公寓走廊。",
                        "support": [summary["fact_id"]],
                    },
                },
                ensure_ascii=False,
            )
        }

    llm = Qwen3VLSceneTextLLM(inference_runner=fake_runner)
    assert llm.runtime_preflight()["status"] == "READY"

    overlay = organize_scene_timeline_narrative_v1(_timeline(), llm)

    assert len(calls) == 1
    assert overlay["status"] == "READY"
    assert overlay["scenes"][0]["readable_title"]["text"] == "公寓走廊"
    assert overlay["scenes"][0]["story_summary"]["text"] == "人物1停留在公寓走廊。"
