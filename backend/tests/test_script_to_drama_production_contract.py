from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.script_to_drama.production import _segment_drafts


SHA = "a" * 64


def _asset(entity_id: str, asset_type: str, roles: list[str]) -> dict:
    return {
        "target_asset_id": f"asset:{entity_id}",
        "target_entity_id": entity_id,
        "asset_type": asset_type,
        "display_name": entity_id,
        "image_prompt": "test prompt",
        "negative_prompt": "",
        "review_prompt_zh": "测试",
        "media": [
            {
                "reference_id": f"ref:{entity_id}:{role}",
                "role": role,
                "storage_relpath": f"test/{entity_id}-{role}.png",
                "sha256": SHA,
                "width": 512,
                "height": 768,
                "mime_type": "image/png",
            }
            for role in roles
        ],
    }


def test_segment_drafts_split_long_shot_and_keep_contiguous_h3_reference_slots() -> None:
    storyboard = {
        "shots": [{
            "shot_id": "SHOT_00001",
            "estimated_seconds": 31.0,
            "character_ids": ["CHAR_A"],
            "scene_id": "SCENE_A",
            "prop_ids": ["PROP_A"],
            "visible_action": "人物进入房间并拿起道具",
            "dialogue_or_voiceover": "你好",
            "shot_size": "中景",
            "camera_angle": "平视",
            "composition": "人物居中",
            "camera_motion": "缓慢推进",
        }]
    }
    images = {"assets": [
        _asset("CHAR_A", "CHARACTER", ["BOARD", "FULL_BODY_FRONT", "FACE"]),
        _asset("SCENE_A", "SCENE", ["LAYOUT"]),
        _asset("PROP_A", "PROP", ["DETAIL"]),
    ]}
    segments = _segment_drafts("project-1", storyboard, images)
    assert len(segments) == 3
    assert all(4_000_000 <= row["duration_us"] <= 15_000_000 for row in segments)
    assert [row["continuation_index"] for row in segments] == [1, 2, 3]
    assert all(row["continuation_count"] == 3 for row in segments)
    for row in segments:
        refs = row["reference_conditions"]
        assert [item["picture_index"] for item in refs] == list(range(1, len(refs) + 1))
        assert [item["reference_role"] for item in refs] == ["FACE", "FULL_BODY_FRONT", "LAYOUT", "DETAIL"]


def test_segment_drafts_refuses_more_than_nine_h3_references() -> None:
    characters = [f"CHAR_{index}" for index in range(5)]
    storyboard = {
        "shots": [{
            "shot_id": "SHOT_00001",
            "estimated_seconds": 5.0,
            "character_ids": characters,
            "scene_id": "SCENE_A",
            "prop_ids": [],
        }]
    }
    images = {"assets": [
        *[_asset(entity_id, "CHARACTER", ["FULL_BODY_FRONT", "FACE"]) for entity_id in characters],
        _asset("SCENE_A", "SCENE", ["LAYOUT"]),
    ]}
    with pytest.raises(AppError) as raised:
        _segment_drafts("project-1", storyboard, images)
    assert raised.value.code == "SCRIPT_TO_DRAMA_REFERENCE_CAPACITY_EXCEEDED"


def test_replica_cannot_invoke_script_to_drama_production(client: TestClient) -> None:
    response = client.post("/api/v3/projects", json={
        "name": "Replica guard",
        "project_type": "REPLICA",
        "source_language": "zh-CN",
        "target_language": "zh-CN",
        "target_region": "CN",
    })
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    run = client.post(
        f"/api/v3/projects/{project_id}/script-to-drama/commands/production/asset_images",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert run.status_code == 422
    assert run.json()["error"]["code"] == "SCRIPT_TO_DRAMA_NOT_ALLOWED"
