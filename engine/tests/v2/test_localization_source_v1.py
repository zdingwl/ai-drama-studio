from __future__ import annotations

from copy import deepcopy

import pytest

from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1
from engine.app.localization_source_v1 import LocalizationSourceError, compose_localization_source_v1


def _read_model() -> dict[str, object]:
    return {
        "schema_version": "breakdown-read-model-v1",
        "timeline": {
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
                "title": "客厅争执",
                "scene_info": {
                    "location": "客厅",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": "窗边有自然光",
                },
                "people": [
                    {"ref": "P1", "display_name": "人物1", "appearance": "黑衣"},
                    {"ref": "P2", "display_name": "人物2", "appearance": "白衣"},
                ],
                "story_summary": "两人在客厅争执。",
                "shots": [{
                    "ordinal": 1,
                    "start_us": 0,
                    "end_us": 1_000_000,
                    "duration_us": 1_000_000,
                    "thumbnail_url": "/thumb.jpg",
                    "reference_url": "/reference.mp4",
                    "visual_description": "P1 站在窗边，P2 拿起花瓶。",
                    "people": ["P1", "P2"],
                    "performance": [{"text": "P2 拿起花瓶", "people": ["P2"]}],
                    "dialogue": [{
                        "start_us": 100_000,
                        "end_us": 300_000,
                        "text": "  原对白，空格也必须保留。  ",
                        "speakers": ["P2"],
                    }],
                    "props": [{"label": "花瓶", "interaction": "拿起"}],
                    "cinematography": {
                        "shot_type": "中景",
                        "composition": "双人构图",
                        "camera_motion": None,
                    },
                    "on_screen_text": [{
                        "start_us": 400_000,
                        "end_us": 500_000,
                        "text": "OCR 原文 100% 保留",
                    }],
                }],
            }],
        },
        "identity": {
            "asset_revision_id": "ASSETREV1",
            "resolved_count": 1,
            "unresolved_count": 1,
            "warnings": ["部分人物尚未完成最终身份确认，当前仍以匿名人物显示。"],
            "scenes": [{
                "scene_ordinal": 1,
                "people": [
                    {"ref": "P1", "display_name": "人物1", "character": None},
                    {
                        "ref": "P2",
                        "display_name": "人物001",
                        "character": {
                            "id": "CHAR1",
                            "name": "人物001",
                            "cover_url": "/character.jpg",
                        },
                    },
                ],
            }],
        },
        "assets": {
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
        },
    }


def _compose(payload: dict[str, object] | None = None) -> dict[str, object]:
    return compose_localization_source_v1(
        payload or _read_model(),
        project_id="PROJECT1",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )


def test_p7_preserves_source_truth_and_projects_only_safe_final_assets() -> None:
    result = _compose()

    assert result["schema_version"] == "localization-source-v1"
    assert result["status"] == "READY_WITH_WARNINGS"
    assert result["source_breakdown_run_id"] == "RUN1"
    assert result["source_shot_revision_id"] == "REV1"
    assert result["source_asset_revision_id"] == "ASSETREV1"
    scene = result["scenes"][0]  # type: ignore[index]
    assert scene["title"] == "客厅争执"
    assert scene["final_scene"]["name"] == "公寓客厅"
    assert [item["display_name"] for item in scene["people"]] == ["人物1", "人物001"]
    shot = scene["shots"][0]
    assert shot["visual_description"] == "P1 站在窗边，P2 拿起花瓶。"
    assert shot["source_dialogue"][0]["source_text"] == "  原对白，空格也必须保留。  "
    assert shot["source_dialogue"][0]["source_key"] == "S1:H1:D1"
    assert shot["source_dialogue"][0]["speakers"][0]["display_name"] == "人物001"
    assert shot["source_on_screen_text"][0]["source_text"] == "OCR 原文 100% 保留"
    assert shot["source_on_screen_text"][0]["source_key"] == "S1:H1:T1"
    assert shot["observed_props"] == [{"label": "花瓶", "interaction": "拿起"}]
    assert shot["final_props"][0]["name"] == "蓝色花瓶"

    # Scene-local P* refs are consumed only as an internal join key and do not leak into person rows.
    assert all(set(item) == {"display_name", "character"} for item in scene["people"])
    assert set(shot["source_dialogue"][0]["speakers"][0]) == {"display_name", "character"}


def test_unresolved_person_stays_anonymous_and_does_not_gain_character_identity() -> None:
    result = _compose()
    scene = result["scenes"][0]  # type: ignore[index]

    assert scene["people"][0] == {"display_name": "人物1", "character": None}
    assert scene["people"][1]["character"]["id"] == "CHAR1"


def test_identity_or_asset_surface_mismatch_is_rejected_instead_of_guessed() -> None:
    bad_identity = _read_model()
    bad_identity["identity"]["scenes"][0]["people"][1]["ref"] = "P3"  # type: ignore[index]
    with pytest.raises(LocalizationSourceError):
        _compose(bad_identity)

    bad_assets = _read_model()
    bad_assets["assets"]["shots"][0]["shot_ordinal"] = 2  # type: ignore[index]
    with pytest.raises(LocalizationSourceError):
        _compose(bad_assets)


def test_character_and_scene_prop_asset_revisions_must_not_disagree() -> None:
    payload = _read_model()
    payload["assets"]["asset_revision_id"] = "ASSETREV2"  # type: ignore[index]

    with pytest.raises(LocalizationSourceError):
        _compose(payload)


def test_non_current_breakdown_cannot_become_localization_source() -> None:
    payload = _read_model()
    payload["timeline"]["is_current"] = False  # type: ignore[index]

    with pytest.raises(LocalizationSourceError):
        _compose(payload)


def test_source_package_contract_does_not_accept_localized_copy_fields() -> None:
    result = _compose()
    mutated = deepcopy(result)
    mutated["scenes"][0]["shots"][0]["source_dialogue"][0]["localized_text"] = "This must live elsewhere"  # type: ignore[index]

    with pytest.raises(ValueError):
        LocalizationSourcePackageV1.model_validate(mutated)
