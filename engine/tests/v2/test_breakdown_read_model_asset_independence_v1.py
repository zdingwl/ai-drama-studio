from __future__ import annotations

from engine.app.breakdown_final_asset_overlay_v1 import FINAL_ASSET_STALE_WARNING
from engine.app.breakdown_read_model_v1 import (
    IDENTITY_STALE_WARNING,
    compose_breakdown_read_model_v1,
)


def _timeline() -> dict[str, object]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "RUN1",
        "source_shot_revision_id": "REV1",
        "episode_id": "EP1",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 1,
        "warnings": [],
        "scenes": [{
            "ordinal": 1,
            "start_us": 0,
            "end_us": 1_000_000,
            "duration_us": 1_000_000,
            "title": "客厅",
            "scene_info": {"location": "客厅", "interior_exterior": "室内", "time_of_day": "白天", "environment": None},
            "people": [{"ref": "P1", "display_name": "人物1", "appearance": None}],
            "story_summary": None,
            "shots": [{
                "ordinal": 1,
                "start_us": 0,
                "end_us": 1_000_000,
                "duration_us": 1_000_000,
                "thumbnail_url": None,
                "reference_url": None,
                "visual_description": "人物站在花瓶旁。",
                "people": ["P1"],
                "performance": [],
                "dialogue": [{"start_us": 100_000, "end_us": 200_000, "text": "原对白", "speakers": []}],
                "props": [{"label": "花瓶", "interaction": None}],
                "cinematography": {"shot_type": None, "composition": None, "camera_motion": None},
                "on_screen_text": [],
            }],
        }],
    }


def _resolution() -> dict[str, object]:
    return {
        "schema_version": "breakdown-character-bridge-v1",
        "profile": "breakdown-character-presence-signature-p5-v1",
        "project_id": "PROJECT1",
        "episode_id": "EP1",
        "breakdown_run_id": "RUN1",
        "shot_revision_id": "REV1",
        "asset_revision_id": "ASSETREV1",
        "scene_count": 1,
        "person_count": 1,
        "resolved_count": 1,
        "unresolved_count": 0,
        "warnings": [],
        "scenes": [{
            "scene_segment_id": "SEG1",
            "scene_ordinal": 1,
            "subject_aware_shot_count": 1,
            "resolved_count": 1,
            "unresolved_count": 0,
            "people": [{
                "scene_person_ref": "P1",
                "local_subject_id": "LS1",
                "local_subject_ordinal": 1,
                "local_display_name": "人物1",
                "status": "RESOLVED",
                "character_id": "CHAR1",
                "character_name": "人物001",
                "support_shot_ids": ["SHOT1"],
                "support_shot_ordinals": [1],
                "resolution_basis": "FINAL_SHOT_BINDING_SIGNATURE_V1",
            }],
        }],
    }


def _asset_overlay() -> dict[str, object]:
    return {
        "asset_revision_id": "ASSETREV1",
        "warnings": [],
        "scenes": [{
            "scene_ordinal": 1,
            "scene": {"id": "SCENE1", "name": "公寓客厅", "cover_url": "/scene.jpg"},
        }],
        "shots": [{
            "scene_ordinal": 1,
            "shot_ordinal": 1,
            "props": [{"id": "PROP1", "name": "蓝色花瓶", "cover_url": None}],
        }],
    }


def test_safe_character_and_final_asset_overlays_can_coexist_without_touching_timeline() -> None:
    timeline = _timeline()
    result = compose_breakdown_read_model_v1(
        timeline,
        _resolution(),
        character_snapshots={
            "CHAR1": {"id": "CHAR1", "name": "人物001", "cover_url": "/character.jpg"},
        },
        asset_overlay=_asset_overlay(),
    )

    assert result["timeline"] == timeline
    assert result["identity"]["resolved_count"] == 1  # type: ignore[index]
    assert result["assets"]["scenes"][0]["scene"]["name"] == "公寓客厅"  # type: ignore[index]
    assert result["assets"]["shots"][0]["props"][0]["name"] == "蓝色花瓶"  # type: ignore[index]


def test_invalid_character_bridge_can_fail_closed_without_removing_safe_scene_prop_assets() -> None:
    bad_resolution = _resolution()
    bad_resolution["breakdown_run_id"] = "OLD_RUN"

    result = compose_breakdown_read_model_v1(
        _timeline(),
        bad_resolution,
        character_snapshots={
            "CHAR1": {"id": "CHAR1", "name": "人物001", "cover_url": None},
        },
        asset_overlay=_asset_overlay(),
    )

    assert result["identity"]["resolved_count"] == 0  # type: ignore[index]
    assert result["identity"]["warnings"] == [IDENTITY_STALE_WARNING]  # type: ignore[index]
    assert result["assets"]["scenes"][0]["scene"]["name"] == "公寓客厅"  # type: ignore[index]
    assert result["assets"]["shots"][0]["props"][0]["name"] == "蓝色花瓶"  # type: ignore[index]


def test_invalid_asset_surface_fails_closed_without_anonymizing_safe_character() -> None:
    bad_assets = _asset_overlay()
    bad_assets["shots"] = [{
        "scene_ordinal": 1,
        "shot_ordinal": 9,
        "props": [{"id": "PROP1", "name": "蓝色花瓶", "cover_url": None}],
    }]

    result = compose_breakdown_read_model_v1(
        _timeline(),
        _resolution(),
        character_snapshots={
            "CHAR1": {"id": "CHAR1", "name": "人物001", "cover_url": None},
        },
        asset_overlay=bad_assets,
    )

    assert result["identity"]["resolved_count"] == 1  # type: ignore[index]
    assert result["identity"]["scenes"][0]["people"][0]["display_name"] == "人物001"  # type: ignore[index]
    assert result["assets"]["asset_revision_id"] is None  # type: ignore[index]
    assert result["assets"]["warnings"] == [FINAL_ASSET_STALE_WARNING]  # type: ignore[index]
    assert result["assets"]["scenes"][0]["scene"] is None  # type: ignore[index]
    assert result["assets"]["shots"][0]["props"] == []  # type: ignore[index]
