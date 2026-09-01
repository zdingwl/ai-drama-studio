from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from engine.app.source_drama_snapshot_contract_v1 import SourceDramaEpisodeSnapshotV1
from engine.app.source_drama_snapshot_v1 import (
    compose_episode_source_drama_snapshot_v1,
    compose_project_source_drama_snapshot_v1,
    source_drama_episode_fingerprint,
)


def _read_model() -> dict:
    return {
        "schema_version": "breakdown-read-model-v1",
        "timeline": {
            "schema_version": "scene-timeline-v1",
            "source_breakdown_run_id": "BREAKDOWN_1",
            "source_shot_revision_id": "SHOTREV_1",
            "episode_id": "EP_1",
            "status": "READY",
            "is_current": True,
            "scene_count": 1,
            "shot_count": 1,
            "warnings": [],
            "scenes": [
                {
                    "ordinal": 1,
                    "start_us": 0,
                    "end_us": 4_000_000,
                    "duration_us": 4_000_000,
                    "title": "客厅",
                    "scene_info": {
                        "location": "客厅",
                        "interior_exterior": "INT",
                        "time_of_day": "DAY",
                        "environment": "现代住宅客厅",
                    },
                    "people": [
                        {
                            "ref": "P1",
                            "display_name": "人物1",
                            "appearance": "年轻女性，长发",
                        },
                        {
                            "ref": "P2",
                            "display_name": "人物2",
                            "appearance": "年轻男性，深色外套",
                        },
                    ],
                    "story_summary": "两人在客厅对话。",
                    "shots": [
                        {
                            "ordinal": 1,
                            "start_us": 0,
                            "end_us": 4_000_000,
                            "duration_us": 4_000_000,
                            "thumbnail_url": "/api/shot-revision-items/ITEM_1/thumbnail",
                            "reference_url": "/api/shot-revision-items/ITEM_1/reference",
                            "visual_description": "女人抬头看向刚进门的男人。",
                            "people": ["P1", "P2"],
                            "performance": [
                                {"text": "人物1抬头看向人物2", "people": ["P1", "P2"]},
                            ],
                            "dialogue": [
                                {
                                    "start_us": 1_000_000,
                                    "end_us": 2_200_000,
                                    "text": "你怎么会在这里？",
                                    "speakers": ["P1"],
                                }
                            ],
                            "props": [
                                {"label": "手机", "interaction": "人物1握在手中"},
                            ],
                            "cinematography": {
                                "shot_type": "MEDIUM",
                                "composition": "双人构图",
                                "camera_motion": "PUSH_IN",
                            },
                            "on_screen_text": [
                                {
                                    "start_us": 0,
                                    "end_us": 1_000_000,
                                    "text": "第一集",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "identity": {
            "asset_revision_id": "ASSETREV_1",
            "resolved_count": 1,
            "unresolved_count": 1,
            "warnings": ["部分人物尚未完成最终身份确认，当前仍以匿名人物显示。"],
            "scenes": [
                {
                    "scene_ordinal": 1,
                    "people": [
                        {
                            "ref": "P1",
                            "display_name": "林晚",
                            "character": {
                                "id": "CHAR_1",
                                "name": "林晚",
                                "cover_url": "/character/1.jpg",
                            },
                        },
                        {
                            "ref": "P2",
                            "display_name": "人物2",
                            "character": None,
                        },
                    ],
                }
            ],
        },
        "assets": {
            "asset_revision_id": "ASSETREV_1",
            "warnings": [],
            "scenes": [
                {
                    "scene_ordinal": 1,
                    "scene": {
                        "id": "SCENE_1",
                        "name": "林家客厅",
                        "cover_url": "/scene/1.jpg",
                    },
                }
            ],
            "shots": [
                {
                    "scene_ordinal": 1,
                    "shot_ordinal": 1,
                    "props": [
                        {
                            "id": "PROP_1",
                            "name": "手机",
                            "cover_url": "/prop/1.jpg",
                        }
                    ],
                }
            ],
        },
    }


def _episode_snapshot(read_model: dict | None = None) -> dict:
    return compose_episode_source_drama_snapshot_v1(
        read_model or _read_model(),
        project_id="PROJECT_1",
        episode_id="EP_1",
        episode_title="第一集",
        episode_order=1,
        source_language="zh-CN",
        revision_items_by_ordinal={
            1: SimpleNamespace(id="ITEM_1", original_shot_id="SHOT_1", ordinal=1),
        },
    )


def test_episode_snapshot_exposes_remake_source_truth_without_legacy_layers() -> None:
    snapshot = _episode_snapshot()

    assert snapshot["schema_version"] == "source-drama-snapshot-v1"
    assert snapshot["source_breakdown_run_id"] == "BREAKDOWN_1"
    assert snapshot["source_shot_revision_id"] == "SHOTREV_1"
    assert snapshot["source_asset_revision_id"] == "ASSETREV_1"
    assert snapshot["shot_count"] == 1
    assert snapshot["resolved_character_count"] == 1
    assert snapshot["unresolved_person_count"] == 1
    assert snapshot["status"] == "READY_WITH_WARNINGS"

    scene = snapshot["scenes"][0]
    shot = scene["shots"][0]
    resolved_person = scene["people"][0]
    unresolved_person = scene["people"][1]

    assert scene["scene_key"].startswith("EP_1:BREAKDOWN_1:S1")
    assert resolved_person["character"]["id"] == "CHAR_1"
    assert unresolved_person["character"] is None
    assert shot["source_shot_id"] == "SHOT_1"
    assert shot["source_revision_item_id"] == "ITEM_1"
    assert shot["reference_url"] == "/api/shot-revision-items/ITEM_1/reference"
    assert shot["source_dialogue"][0]["source_text"] == "你怎么会在这里？"
    assert shot["source_dialogue"][0]["speakers"] == [resolved_person["person_key"]]
    assert shot["final_props"][0]["id"] == "PROP_1"
    assert scene["final_scene"]["id"] == "SCENE_1"
    assert len(snapshot["source_fingerprint"]) == 64


def test_episode_fingerprint_is_stable_and_changes_with_source_fact() -> None:
    first = _episode_snapshot()
    second = _episode_snapshot()
    assert first["source_fingerprint"] == second["source_fingerprint"]

    changed = _read_model()
    changed["timeline"]["scenes"][0]["shots"][0]["dialogue"][0]["text"] = "你为什么在这里？"
    third = _episode_snapshot(changed)
    assert first["source_fingerprint"] != third["source_fingerprint"]


def test_target_side_fields_are_forbidden_from_source_snapshot() -> None:
    payload = _episode_snapshot()
    payload["target_language"] = "en-US"
    with pytest.raises(ValidationError):
        SourceDramaEpisodeSnapshotV1.model_validate(payload)


def test_project_snapshot_deduplicates_resolved_character_catalog() -> None:
    episode = _episode_snapshot()
    project = compose_project_source_drama_snapshot_v1(
        project_id="PROJECT_1",
        project_name="测试短剧",
        source_language="zh-CN",
        episodes=[episode],
    )

    assert project["schema_version"] == "source-drama-project-snapshot-v1"
    assert project["episode_count"] == 1
    assert project["shot_count"] == 1
    assert project["resolved_character_count"] == 1
    assert project["characters"] == [
        {"id": "CHAR_1", "name": "林晚", "cover_url": "/character/1.jpg"}
    ]
    assert project["source_fingerprint"]


def test_fingerprint_ignores_operational_status_and_warning_text() -> None:
    first = _episode_snapshot()
    changed = deepcopy(first)
    changed["warnings"] = ["另一条仅用于展示的运行提示"]
    changed["status"] = "READY_WITH_WARNINGS"

    assert source_drama_episode_fingerprint(changed) == first["source_fingerprint"]
