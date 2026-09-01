from __future__ import annotations

from engine.app.breakdown_final_asset_overlay_v1 import (
    FINAL_ASSET_STALE_WARNING,
    compose_final_asset_overlay_v1,
)


def _timeline() -> dict[str, object]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "RUN1",
        "source_shot_revision_id": "REV1",
        "episode_id": "EP1",
        "status": "READY",
        "is_current": True,
        "scene_count": 2,
        "shot_count": 3,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 2_000_000,
                "duration_us": 2_000_000,
                "title": "客厅争执",
                "scene_info": {"location": "客厅", "interior_exterior": "室内", "time_of_day": "白天", "environment": None},
                "people": [],
                "story_summary": None,
                "shots": [
                    {
                        "ordinal": 1, "start_us": 0, "end_us": 1_000_000, "duration_us": 1_000_000,
                        "thumbnail_url": None, "reference_url": None, "visual_description": "桌上有花瓶。",
                        "people": [], "performance": [], "dialogue": [],
                        "props": [{"label": "花瓶", "interaction": None}],
                        "cinematography": {"shot_type": None, "composition": None, "camera_motion": None},
                        "on_screen_text": [],
                    },
                    {
                        "ordinal": 2, "start_us": 1_000_000, "end_us": 2_000_000, "duration_us": 1_000_000,
                        "thumbnail_url": None, "reference_url": None, "visual_description": "人物拿起手提包。",
                        "people": [], "performance": [], "dialogue": [],
                        "props": [{"label": "手提包", "interaction": "拿起"}],
                        "cinematography": {"shot_type": None, "composition": None, "camera_motion": None},
                        "on_screen_text": [],
                    },
                ],
            },
            {
                "ordinal": 2,
                "start_us": 2_000_000,
                "end_us": 3_000_000,
                "duration_us": 1_000_000,
                "title": "走廊",
                "scene_info": {"location": "走廊", "interior_exterior": "室内", "time_of_day": "白天", "environment": None},
                "people": [],
                "story_summary": None,
                "shots": [
                    {
                        "ordinal": 3, "start_us": 2_000_000, "end_us": 3_000_000, "duration_us": 1_000_000,
                        "thumbnail_url": None, "reference_url": None, "visual_description": "空走廊。",
                        "people": [], "performance": [], "dialogue": [], "props": [],
                        "cinematography": {"shot_type": None, "composition": None, "camera_motion": None},
                        "on_screen_text": [],
                    }
                ],
            },
        ],
    }


def _kwargs() -> dict[str, object]:
    return {
        "asset_revision_id": "ASSETREV1",
        "shot_id_by_ordinal": {1: "S1", 2: "S2", 3: "S3"},
        "scene_binding_by_shot": {"S1": "SCENE_A", "S2": "SCENE_A", "S3": "SCENE_B"},
        "prop_bindings_by_shot": {"S1": ["PROP_A"], "S2": ["PROP_A", "PROP_B"], "S3": []},
        "scene_snapshots": {
            "SCENE_A": {"id": "SCENE_A", "name": "公寓客厅", "cover_url": "/scene-a.jpg"},
            "SCENE_B": {"id": "SCENE_B", "name": "公寓走廊", "cover_url": None},
            "SCENE_C": {"id": "SCENE_C", "name": "卧室", "cover_url": None},
        },
        "prop_snapshots": {
            "PROP_A": {"id": "PROP_A", "name": "蓝色花瓶", "cover_url": None},
            "PROP_B": {"id": "PROP_B", "name": "黑色手提包", "cover_url": None},
        },
    }


def test_exact_final_bindings_project_scene_and_shot_props() -> None:
    overlay = compose_final_asset_overlay_v1(_timeline(), **_kwargs())  # type: ignore[arg-type]

    assert overlay.asset_revision_id == "ASSETREV1"
    assert overlay.warnings == []
    assert overlay.scenes[0].scene is not None
    assert overlay.scenes[0].scene.name == "公寓客厅"
    assert overlay.scenes[1].scene is not None
    assert overlay.scenes[1].scene.name == "公寓走廊"
    assert [item.name for item in overlay.shots[0].props] == ["蓝色花瓶"]
    assert [item.name for item in overlay.shots[1].props] == ["蓝色花瓶", "黑色手提包"]
    assert overlay.shots[2].props == []


def test_scene_conflict_only_suppresses_that_scene_not_safe_prop_bindings() -> None:
    kwargs = _kwargs()
    kwargs["scene_binding_by_shot"] = {"S1": "SCENE_A", "S2": "SCENE_C", "S3": "SCENE_B"}

    overlay = compose_final_asset_overlay_v1(_timeline(), **kwargs)  # type: ignore[arg-type]

    assert overlay.scenes[0].scene is None
    assert overlay.scenes[1].scene is not None
    assert overlay.scenes[1].scene.name == "公寓走廊"
    assert [item.name for item in overlay.shots[1].props] == ["蓝色花瓶", "黑色手提包"]
    assert overlay.warnings == []


def test_missing_scene_binding_keeps_g2_scene_title_without_guessing() -> None:
    kwargs = _kwargs()
    kwargs["scene_binding_by_shot"] = {"S1": "SCENE_A", "S3": "SCENE_B"}

    overlay = compose_final_asset_overlay_v1(_timeline(), **kwargs)  # type: ignore[arg-type]

    assert overlay.scenes[0].scene is None
    assert overlay.scenes[1].scene is not None
    assert overlay.warnings == []


def test_shot_revision_surface_mismatch_fails_closed_for_whole_asset_overlay() -> None:
    kwargs = _kwargs()
    kwargs["shot_id_by_ordinal"] = {1: "S1", 2: "S2"}

    overlay = compose_final_asset_overlay_v1(_timeline(), **kwargs)  # type: ignore[arg-type]

    assert overlay.asset_revision_id is None
    assert overlay.warnings == [FINAL_ASSET_STALE_WARNING]
    assert all(item.scene is None for item in overlay.scenes)
    assert all(item.props == [] for item in overlay.shots)


def test_binding_to_missing_final_prop_fails_closed_instead_of_using_g2_label() -> None:
    kwargs = _kwargs()
    kwargs["prop_snapshots"] = {
        "PROP_A": {"id": "PROP_A", "name": "蓝色花瓶", "cover_url": None},
    }

    overlay = compose_final_asset_overlay_v1(_timeline(), **kwargs)  # type: ignore[arg-type]

    assert overlay.warnings == [FINAL_ASSET_STALE_WARNING]
    assert all(item.props == [] for item in overlay.shots)
    # Frozen G2 labels are not consumed as a fallback identity key by this overlay.
    assert _timeline()["scenes"][0]["shots"][1]["props"][0]["label"] == "手提包"  # type: ignore[index]


def test_no_asset_revision_means_no_final_asset_projection() -> None:
    kwargs = _kwargs()
    kwargs["asset_revision_id"] = None

    overlay = compose_final_asset_overlay_v1(_timeline(), **kwargs)  # type: ignore[arg-type]

    assert overlay.asset_revision_id is None
    assert overlay.warnings == []
    assert all(item.scene is None for item in overlay.scenes)
    assert all(item.props == [] for item in overlay.shots)
